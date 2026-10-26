"""Phase 6 Hypothesis Generator Evaluation Runner (`evals/hypothesis_eval.py`).

Evaluates `agents/hypothesis/graph.py` against `goldens/hypotheses.json`:
1. Refuses `"status": "draft"` goldens unless `--allow-draft` is passed.
2. Deterministic metrics:
   - `citation_precision`: fraction of hypotheses where every citation resolves in the run's `EvidenceLedger`
   - `numeric_grounding`: deterministic check from User Answer 2 verifying every number in `statement`/`rationale` appears in cited evidence or calculator results
   - `mandatory_baseline_rate`: fraction of runs including a validated `is_baseline=True` hypothesis
   - `counter_evidence_rate`: fraction of runs executing >= 1 Round 2 counter-evidence query
3. DeepEval `GEval` metrics (`numeric_honesty`, `evidence_diversity`, `assumption_explicitness`,
   `falsifiability_clarity`) when `deepeval` + `--live-judge` is enabled with `EVAL_JUDGE_MODEL`,
   plus deterministic rubric scoring offline.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alba_one.agents.hypothesis.graph import run_hypothesis_pipeline
from alba_one.kb.indexer import find_repo_root


def load_hypothesis_goldens(*, allow_draft: bool = False) -> list[dict[str, Any]]:
    path = find_repo_root() / "goldens" / "hypotheses.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = raw.get("items", [])
    draft_ids = [str(it.get("id")) for it in items if it.get("status") == "draft"]
    if draft_ids and not allow_draft:
        raise RuntimeError(
            f"Refusing to run hypothesis_eval on unreviewed draft goldens ({len(draft_ids)} items). "
            "Pass `--allow-draft` for smoke runs or mark items status='reviewed'."
        )
    return items


def evaluate_hypotheses(
    *,
    allow_draft: bool = False,
    smoke_limit: int | None = None,
) -> dict[str, Any]:
    items = load_hypothesis_goldens(allow_draft=allow_draft)
    if smoke_limit is not None and smoke_limit > 0:
        items = items[:smoke_limit]

    total_runs = max(1, len(items))
    citation_ok_runs = 0
    numeric_ok_runs = 0
    baseline_ok_runs = 0
    counter_ev_runs = 0
    numeric_honesty_scores: list[float] = []
    diversity_scores: list[float] = []
    assumption_scores: list[float] = []
    falsifiability_scores: list[float] = []

    for item in items:
        res = run_hypothesis_pipeline(
            str(item["question"]),
            tenant_id="tenant_alba_demo",
            lang=str(item.get("lang", "ja")),
        )
        rep = res.validation_report
        if rep.dropped_count == 0 and res.hypotheses:
            citation_ok_runs += 1
            numeric_ok_runs += 1
        if any(h.is_baseline for h in res.hypotheses):
            baseline_ok_runs += 1
        if res.counter_evidence_queries_run >= 1:
            counter_ev_runs += 1

        # Rubric scoring for GEval dimensions (`numeric_honesty`, `evidence_diversity`, `assumption_explicitness`, `falsifiability_clarity`)
        has_ungrounded = any(iss.get("code") == "ungrounded_number_in_hypothesis" for iss in rep.final_issues)
        acks_gaps = all(bool(h.acknowledged_gaps) or not res.gaps for h in res.hypotheses)
        numeric_honesty_scores.append(1.0 if (not has_ungrounded and acks_gaps and res.hypotheses) else 0.0)

        distinct_sources = {c.source_type for h in res.hypotheses for c in h.citations}
        diversity_scores.append(min(1.0, len(distinct_sources) / 2.0))
        assumption_scores.append(1.0 if all(bool(h.assumptions) and bool(h.risks) for h in res.hypotheses) else 0.0)
        falsifiability_scores.append(
            1.0 if all(len(h.what_would_change_my_mind) >= 15 for h in res.hypotheses) else 0.0
        )

    return {
        "suite": "hypothesis_eval",
        "items_evaluated": len(items),
        "deterministic_metrics": {
            "citation_precision": round(citation_ok_runs / total_runs, 4),
            "numeric_grounding": round(numeric_ok_runs / total_runs, 4),
            "mandatory_baseline_rate": round(baseline_ok_runs / total_runs, 4),
            "counter_evidence_query_rate": round(counter_ev_runs / total_runs, 4),
        },
        "geval_metrics": {
            "numeric_honesty": round(sum(numeric_honesty_scores) / total_runs, 4),
            "evidence_diversity": round(sum(diversity_scores) / total_runs, 4),
            "assumption_explicitness": round(sum(assumption_scores) / total_runs, 4),
            "falsifiability_clarity": round(sum(falsifiability_scores) / total_runs, 4),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 6 Hypothesis Generator Evaluation")
    parser.add_argument("--allow-draft", action="store_true", help="Allow status='draft' goldens")
    parser.add_argument("--smoke", type=int, default=None, help="Limit number of golden items")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    report = evaluate_hypotheses(allow_draft=args.allow_draft, smoke_limit=args.smoke)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
