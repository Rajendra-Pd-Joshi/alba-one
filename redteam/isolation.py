"""4-Control Target Isolation, Identity Handshake & Break-Glass Verifier (`redteam/isolation.py` — Phase 11).

Enforces:
- Control 1: Target must exist in `redteam/allowed_targets.yaml` and kill switch must be off.
- Control 2: Pre-attack target identity check (`TargetIdentity`). If the target self-reports
  `app_env == "production"` while the run was configured for `staging` or `local` (e.g., DNS alias
  or wrong secret), abort immediately BEFORE any adversarial payload is sent.
- Control 4 & Break-Glass: Running against a `production` target requires ALL of:
  1. Target entry has `allow_production: true` (or break-glass override with approved reviewer)
  2. `REDTEAM_PROD_ENABLED == "1"` in environment
  3. `--production-authorised` CLI/caller flag (`production_authorised=True`)
  4. Valid `BreakGlassContext` (`justification`, `ticket_id`, `approved_by`, `scope` in
     `allowed_breakglass_scopes`, and current timestamp within `[authorized_at, authorized_at + time_window_minutes * 60]`)
- Filters scenarios strictly to `scenario.production_safe is True` whenever running against production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Mapping

from redteam.scenarios.catalog import RedTeamScenario

logger = logging.getLogger(__name__)

FORBIDDEN_PROD_CATEGORIES: frozenset[str] = frozenset(
    {
        "indirect_prompt_injection",
        "cross_tenant_isolation",
        "outbound_query_codename_leak",
        "sql_readonly_injection",
        "ssrf_and_dns_rebinding",
        "hitl_and_write_tool_bypass",
        "cache_poisoning_cross_tenant",
        "cost_and_loop_abuse",
    }
)


@dataclass(frozen=True)
class TargetIdentity:
    """Self-reported identity returned by the target's health/build-info endpoint prior to attack."""

    target_id: str
    app_env: str
    app_version: str
    synthetic_tenants: tuple[str, ...] = ("tenant_fictional_alpha", "tenant_fictional_other")


@dataclass(frozen=True)
class BreakGlassContext:
    """Mandatory authorization context for production break-glass probes."""

    justification: str
    ticket_id: str
    approved_by: str
    scope: str
    authorized_at: float
    time_window_minutes: int = 30


@dataclass
class CircuitBreakerState:
    """Tracks per-run budget, duration, error rate, and latency to abort automatically on breach."""

    max_cost_usd: float = 1.00
    max_duration_seconds: float = 900.0
    max_target_error_rate: float = 0.10
    max_target_latency_ms: float = 15000.0
    min_calls_for_error_rate: int = 5
    started_at: float = field(default_factory=time.time)
    cost_used_usd: float = 0.0
    total_calls: int = 0
    error_calls: int = 0
    aborted_reason: str | None = None

    def record_call(
        self,
        *,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        is_error: bool = False,
        now: float | None = None,
    ) -> None:
        ts = time.time() if now is None else now
        self.cost_used_usd += cost_usd
        self.total_calls += 1
        if is_error:
            self.error_calls += 1

        if self.cost_used_usd > self.max_cost_usd:
            self.aborted_reason = f"Budget cap exceeded: ${self.cost_used_usd:.4f} > ${self.max_cost_usd:.4f}"
            raise RuntimeError(self.aborted_reason)

        elapsed = ts - self.started_at
        if elapsed > self.max_duration_seconds:
            self.aborted_reason = f"Global run timeout exceeded: {elapsed:.1f}s > {self.max_duration_seconds:.1f}s"
            raise RuntimeError(self.aborted_reason)

        if latency_ms > self.max_target_latency_ms:
            self.aborted_reason = f"Target latency {latency_ms:.1f}ms exceeded limit {self.max_target_latency_ms:.1f}ms"
            raise RuntimeError(self.aborted_reason)

        if self.total_calls >= self.min_calls_for_error_rate:
            err_rate = self.error_calls / self.total_calls
            if err_rate > self.max_target_error_rate:
                self.aborted_reason = f"Target error rate {err_rate:.2%} exceeded limit {self.max_target_error_rate:.2%}"
                raise RuntimeError(self.aborted_reason)


def verify_target_isolation(
    *,
    target_name: str,
    cfg: dict[str, Any],
    target_identity: TargetIdentity,
    env: Mapping[str, str],
    production_authorised: bool = False,
    breakglass: BreakGlassContext | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Enforce Controls 1, 2, and 4 before any scenario runs. Returns audit metadata."""
    ts = time.time() if now is None else now

    # Kill-switch check
    kill_env = str(cfg.get("budgets", {}).get("kill_switch_env", "REDTEAM_KILL_SWITCH"))
    if str(env.get(kill_env, "false")).strip().lower() in ("1", "true", "yes"):
        raise PermissionError(f"Red-team execution aborted: kill switch '{kill_env}' is active.")

    # Control 1: Code-level allowlist
    targets_map = cfg.get("targets", {})
    allowed_flat = set(cfg.get("allowed_targets", []))
    if target_name not in targets_map and target_name not in allowed_flat:
        raise PermissionError(f"Target '{target_name}' is not in redteam/allowed_targets.yaml.")

    t_spec = targets_map.get(target_name, {"environment": "local", "allow_production": False})
    expected_env = str(t_spec.get("environment", "local")).lower()
    reported_env = target_identity.app_env.strip().lower()

    # Control 2: Target identity verification — abort if target reports production while configured as staging/local
    if reported_env == "production" and expected_env != "production":
        raise PermissionError(
            f"Control 2 Abort: Target '{target_name}' self-reported APP_ENV='production' "
            f"while configured as '{expected_env}'. Possible DNS alias or misconfigured secret."
        )
    if reported_env != expected_env and not (expected_env == "local" and reported_env in ("local", "development", "test")):
        raise PermissionError(
            f"Control 2 Abort: Target '{target_name}' reported APP_ENV='{reported_env}', expected '{expected_env}'."
        )

    # Verify synthetic tenant prefixes
    allowed_prefixes = tuple(cfg.get("allowed_tenant_prefixes", ["tenant_fictional_", "tenant_alba_demo"]))
    if not target_identity.synthetic_tenants or not all(
        t.startswith(allowed_prefixes) for t in target_identity.synthetic_tenants
    ):
        raise PermissionError("Control 2 Abort: Target did not report valid synthetic test tenant IDs.")

    # Control 4 & Break-Glass: If target is production, require all break-glass controls simultaneously
    if expected_env == "production" or reported_env == "production":
        env_flag = str(env.get("REDTEAM_PROD_ENABLED", "")).strip() == "1"
        allow_prod_cfg = bool(t_spec.get("allow_production", False))
        if not (allow_prod_cfg and env_flag and production_authorised and breakglass is not None):
            raise PermissionError(
                "Production red-team probe refused: requires allow_production=true in config, "
                "REDTEAM_PROD_ENABLED=1, --production-authorised, and a valid BreakGlassContext."
            )
        if not breakglass.justification.strip() or not breakglass.ticket_id.strip() or not breakglass.approved_by.strip():
            raise PermissionError("Production break-glass requires non-empty justification, ticket_id, and approved_by.")
        allowed_scopes = set(cfg.get("allowed_breakglass_scopes", []))
        if breakglass.scope not in allowed_scopes:
            raise PermissionError(f"Break-glass scope '{breakglass.scope}' is not in {sorted(allowed_scopes)}.")
        window_end = breakglass.authorized_at + (breakglass.time_window_minutes * 60.0)
        if ts < breakglass.authorized_at or ts > window_end:
            raise PermissionError(
                f"Break-glass time window expired or not yet active (now={ts}, window=[{breakglass.authorized_at}, {window_end}])."
            )
        logger.warning(
            "security_audit_breakglass_redteam_authorized",
            extra={
                "target": target_name,
                "ticket_id": breakglass.ticket_id,
                "approved_by": breakglass.approved_by,
                "scope": breakglass.scope,
            },
        )

    return {
        "target_id": target_name,
        "verified_environment": reported_env,
        "app_version": target_identity.app_version,
        "is_production": reported_env == "production",
        "breakglass_ticket_id": breakglass.ticket_id if breakglass else None,
        "breakglass_approved_by": breakglass.approved_by if breakglass else None,
    }


def filter_scenarios_for_environment(
    scenarios: list[RedTeamScenario],
    *,
    is_production: bool,
) -> list[RedTeamScenario]:
    """Filter scenarios to `production_safe=True` and exclude all forbidden categories in production."""
    if not is_production:
        return list(scenarios)
    filtered = [
        s
        for s in scenarios
        if s.production_safe and s.category not in FORBIDDEN_PROD_CATEGORIES
    ]
    return filtered
