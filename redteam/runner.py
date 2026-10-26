"""Red-Team Harness Runner (`redteam/runner.py` — Phase 9 & Phase 11).

Enforces:
- 4-Control Target Isolation (`redteam/isolation.py` + `redteam/allowed_targets.yaml`).
- Pre-attack TargetIdentity check: aborts immediately if target self-reports `production`
  when configured as `staging`/`local`.
- Production break-glass: requires `allow_production: true`, `REDTEAM_PROD_ENABLED=1`,
  `--production-authorised`, valid `BreakGlassContext` within declared time window, and
  filters strictly to `scenario.production_safe is True`.
- Never claims `"secure"` in reports: outputs the exact factual summary:
  `"no critical bypass observed in <N> scenarios × <R> repeats on <date/version>"`.
- Produces `redteam_runs` and `redteam_results` audit rows, per-language (`ja`/`en`) false-positive
  rates, and re-runs failing scenarios `repro_repeats` times to measure reproduction rate.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any

import yaml

from alba_one.kb.indexer import find_repo_root
from redteam.fixtures.generator import generate_canary_bundle
from redteam.isolation import (
    BreakGlassContext,
    CircuitBreakerState,
    TargetIdentity,
    filter_scenarios_for_environment,
    verify_target_isolation,
)
from redteam.scenarios.catalog import (
    build_redteam_scenario_catalog,
    compute_scenario_set_hash,
)
from redteam.scorers import score_execution_trace
from redteam.targets import DeliberatelyVulnerableTarget, RedTeamTargetPort, SafeTarget

SCORER_VERSION = "2026-10-24.v1"


def validate_allowed_target(target_name: str, config_path: str | Path | None = None) -> dict[str, Any]:
    """Verify `target_name` is in `redteam/allowed_targets.yaml` and kill switch is off."""
    path = Path(config_path) if config_path else (find_repo_root() / "redteam" / "allowed_targets.yaml")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    kill_env = str(cfg.get("budgets", {}).get("kill_switch_env", "REDTEAM_KILL_SWITCH"))
    if os.getenv(kill_env, "false").lower() in ("1", "true", "yes"):
        raise PermissionError(f"Red-team execution aborted: kill switch '{kill_env}' is active.")

    allowed = set(cfg.get("allowed_targets", []))
    if target_name not in allowed and target_name not in cfg.get("targets", {}):
        raise PermissionError(
            f"Red-team target '{target_name}' is not in redteam/allowed_targets.yaml ({sorted(allowed)})."
        )
    return cfg


def run_redteam_suite(
    *,
    target_name: str = "in_process_safe",
    repeats: int | None = None,
    layer_filter: str | None = None,
    smoke_per_family: int | None = None,
    app_version: str = "1.0.0",
    target_identity: TargetIdentity | None = None,
    production_authorised: bool = False,
    breakglass: BreakGlassContext | None = None,
    triggered_by: str = "ci_runner",
    trigger_kind: str = "scheduled",
    repro_repeats: int = 2,
    config_override: dict[str, Any] | None = None,
    env_override: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute the red-team suite across `repeats` with 4-control target isolation and audit recording."""
    t0 = time.time()
    cfg = config_override or validate_allowed_target(target_name)
    env_map = env_override if env_override is not None else dict(os.environ)

    default_env = str(cfg.get("targets", {}).get(target_name, {}).get("environment", "local"))
    identity = target_identity or TargetIdentity(
        target_id=target_name,
        app_env=default_env,
        app_version=app_version,
        synthetic_tenants=("tenant_fictional_canary",) if default_env == "production" else ("tenant_fictional_alpha", "tenant_fictional_other"),
    )
    isolation_audit = verify_target_isolation(
        target_name=target_name,
        cfg=cfg,
        target_identity=identity,
        env=env_map,
        production_authorised=production_authorised,
        breakglass=breakglass,
    )

    budgets = cfg.get("budgets", {})
    num_repeats = repeats if repeats is not None else int(env_map.get("REDTEAM_REPEATS", budgets.get("default_repeats", 3)))
    breaker = CircuitBreakerState(
        max_cost_usd=float(budgets.get("max_cost_usd_per_run", 1.00)),
        max_duration_seconds=float(budgets.get("max_run_duration_seconds", 900.0)),
        max_target_error_rate=float(budgets.get("max_target_error_rate", 0.10)),
        max_target_latency_ms=float(budgets.get("max_target_latency_ms", 15000.0)),
        started_at=t0,
    )

    target: RedTeamTargetPort = (
        DeliberatelyVulnerableTarget() if target_name == "in_process_vulnerable" else SafeTarget()
    )

    all_scenarios = filter_scenarios_for_environment(
        build_redteam_scenario_catalog(),
        is_production=bool(isolation_audit["is_production"]),
    )
    if layer_filter in ("layer1_deterministic", "layer2_behavioral"):
        all_scenarios = [s for s in all_scenarios if s.layer_gate == layer_filter]
    if smoke_per_family is not None and smoke_per_family > 0:
        by_fam: dict[str, list[Any]] = {}
        for s in all_scenarios:
            lst = by_fam.setdefault(s.category, [])
            if len(lst) < smoke_per_family:
                lst.append(s)
        all_scenarios = [s for lst in by_fam.values() for s in lst]

    run_id = f"rt_run_{uuid.uuid4().hex[:12]}"
    critical_bypasses = 0
    by_family_stats: dict[str, dict[str, int]] = {}
    by_lang_stats: dict[str, dict[str, int]] = {"ja": {"runs": 0, "bypasses": 0}, "en": {"runs": 0, "bypasses": 0}}
    blocking_layer_counts: dict[str, int] = {}
    results_rows: list[dict[str, Any]] = []
    failing_scenarios_map: dict[str, Any] = {}

    for r_idx in range(num_repeats):
        bundle = generate_canary_bundle(seed_hex=f"RUN{r_idx + 1:02d}FICTIONAL00")
        for sc in all_scenarios:
            trace = target.execute_scenario(sc, bundle)
            breaker.record_call(cost_usd=0.0001, latency_ms=5.0, is_error=False)
            score = score_execution_trace(trace, bundle)

            f_stat = by_family_stats.setdefault(sc.category, {"runs": 0, "critical_bypasses": 0})
            f_stat["runs"] += 1
            by_lang_stats[sc.language]["runs"] += 1

            if score.critical_bypass:
                critical_bypasses += 1
                f_stat["critical_bypasses"] += 1
                by_lang_stats[sc.language]["bypasses"] += 1
                failing_scenarios_map[sc.id] = sc
            elif score.blocking_layer:
                blocking_layer_counts[score.blocking_layer] = blocking_layer_counts.get(score.blocking_layer, 0) + 1

            results_rows.append(
                {
                    "result_id": f"{run_id}_{sc.id}_r{r_idx + 1}",
                    "run_id": run_id,
                    "scenario_id": sc.id,
                    "category": sc.category,
                    "language": sc.language,
                    "repeat_index": r_idx + 1,
                    "critical_bypass": score.critical_bypass,
                    "blocking_layer": score.blocking_layer,
                    "reasons": score.violated_scorers,
                    "trace_id": f"tr_{run_id}_{sc.id}_{r_idx + 1}",
                }
            )

    # Re-run failing scenarios `repro_repeats` times to measure reproduction rate (never lowers severity)
    reproduction_rates: dict[str, float] = {}
    if failing_scenarios_map and repro_repeats > 0:
        for sid, sc in failing_scenarios_map.items():
            repro_hits = 0
            for rr in range(repro_repeats):
                b_repro = generate_canary_bundle(seed_hex=f"REPRO{rr + 1:02d}FICT00")
                sc_repro = score_execution_trace(target.execute_scenario(sc, b_repro), b_repro)
                if sc_repro.critical_bypass:
                    repro_hits += 1
            reproduction_rates[sid] = round(repro_hits / repro_repeats, 4)

    benign_path = find_repo_root() / "redteam" / "fixtures" / "benign_ja_en.json"
    benign_raw = benign_path.read_text(encoding="utf-8")
    dataset_hash = hashlib.sha256(benign_raw.encode("utf-8")).hexdigest()[:16]
    benign_items = json.loads(benign_raw).get("items", [])
    fp_by_lang: dict[str, dict[str, int]] = {"ja": {"blocked": 0, "total": 0}, "en": {"blocked": 0, "total": 0}}
    false_positives = 0
    for it in benign_items:
        lang_k = str(it["lang"])
        fp_by_lang.setdefault(lang_k, {"blocked": 0, "total": 0})["total"] += 1
        if target.execute_benign_prompt(str(it["prompt"]), lang_k):
            false_positives += 1
            fp_by_lang[lang_k]["blocked"] += 1

    fp_rate = round(false_positives / max(1, len(benign_items)), 4)
    duration_s = round(max(0.001, time.time() - t0), 3)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n_scen = len(all_scenarios)
    statement = (
        f"no critical bypass observed in {n_scen} scenarios × {num_repeats} repeats on {today_str}/{app_version}"
        if critical_bypasses == 0
        else f"{critical_bypasses} critical bypass(es) observed in {n_scen} scenarios × {num_repeats} repeats on {today_str}/{app_version}"
    )
    scen_hash = compute_scenario_set_hash(all_scenarios)

    run_record = {
        "run_id": run_id,
        "triggered_by": triggered_by,
        "trigger_kind": "breakglass" if breakglass else trigger_kind,
        "target_id": target_name,
        "verified_environment": isolation_audit["verified_environment"],
        "app_version": app_version,
        "scenario_set_hash": scen_hash,
        "dataset_hash": dataset_hash,
        "scorer_version": SCORER_VERSION,
        "repeats": num_repeats,
        "critical_bypass_count": critical_bypasses,
        "false_positive_rate": fp_rate,
        "budget_used_usd": round(breaker.cost_used_usd, 6),
        "duration_seconds": duration_s,
        "outcome": "passed" if critical_bypasses == 0 else "failed",
        "breakglass_ticket_id": isolation_audit["breakglass_ticket_id"],
        "breakglass_approved_by": isolation_audit["breakglass_approved_by"],
    }

    return {
        "run_id": run_id,
        "target": target_name,
        "verified_environment": isolation_audit["verified_environment"],
        "gate_passed": critical_bypasses == 0,
        "statement": statement,
        "scenarios_count": n_scen,
        "repeats": num_repeats,
        "total_executions": n_scen * num_repeats,
        "critical_bypasses": critical_bypasses,
        "reproduction_rates": reproduction_rates,
        "benign_false_positive_rate": fp_rate,
        "benign_stats_by_lang": fp_by_lang,
        "blocking_layer_attribution": blocking_layer_counts,
        "by_language": {
            lang: {
                **stats,
                "asr": round(stats["bypasses"] / max(1, stats["runs"]), 4),
                "false_positive_rate": round(fp_by_lang[lang]["blocked"] / max(1, fp_by_lang[lang]["total"]), 4),
            }
            for lang, stats in by_lang_stats.items()
        },
        "by_family": {
            fam: {**stats, "asr": round(stats["critical_bypasses"] / max(1, stats["runs"]), 4)}
            for fam, stats in by_family_stats.items()
        },
        "measured_cost_usd": round(breaker.cost_used_usd, 6),
        "duration_seconds": duration_s,
        "redteam_run_row": run_record,
        "redteam_result_rows": results_rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Red-Team Harness Runner")
    parser.add_argument("--target", default="in_process_safe")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--layer", default=None, choices=["layer1_deterministic", "layer2_behavioral"])
    parser.add_argument("--smoke", type=int, default=None, help="Scenarios per family")
    parser.add_argument("--production-authorised", action="store_true")
    args = parser.parse_args(argv)

    rep = run_redteam_suite(
        target_name=args.target,
        repeats=args.repeats,
        layer_filter=args.layer,
        smoke_per_family=args.smoke,
        production_authorised=args.production_authorised,
    )
    summary = {k: v for k, v in rep.items() if k != "redteam_result_rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if rep["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
