"""FastAPI router for Operational Metrics & Evaluation Reports (`api/metrics.py`).

Per Phase 9 User Answer 1:
- `GET /api/v1/metrics/decisions/{decision_id}`: per-stage breakdown for a decision run (tenant-scoped).
- `GET /api/v1/metrics/summary?from_ts&to_ts&group_by=stage|model|tool|tenant`:
  tenant-scoped summary using `percentile_cont` (`group_by=tenant` is strictly `admin`-only;
  non-admin callers receive HTTP 403).
- `GET /api/v1/evals`: reads the JSON evaluation reports and `eval_runs` records.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from alba_one.core.tenancy import get_tenant_context, get_user_context
from alba_one.kb.indexer import find_repo_root
from alba_one.observability.queries import aggregate_decision_run_metrics, summarize_spans_grouped
from alba_one.observability.telemetry import BoundedSpanTelemetryRecorder
from alba_one.schemas.common import TenantContext, UserContext, UserRole

router = APIRouter(tags=["metrics", "evals"])
_global_telemetry: BoundedSpanTelemetryRecorder | None = None


def get_telemetry_recorder() -> BoundedSpanTelemetryRecorder:
    global _global_telemetry
    if _global_telemetry is None:
        _global_telemetry = BoundedSpanTelemetryRecorder()
    return _global_telemetry


@router.get("/api/v1/metrics/decisions/{decision_id}")
async def get_decision_metrics_endpoint(
    decision_id: str,
    run_id: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return per-stage latency, tokens, cost (USD & configured JPY), retries, and unpriced call count."""
    rec = get_telemetry_recorder()
    all_spans = list(rec.flushed_spans) + list(rec.queue)
    metrics = aggregate_decision_run_metrics(
        all_spans,
        run_id=run_id or f"run_{decision_id}",
        decision_id=decision_id,
        tenant_id=tenant.tenant_id,
    )
    return {
        "requested_by": user.user_id,
        "telemetry_health": rec.health_counters(),
        "metrics": metrics.to_dict(),
    }


@router.get("/api/v1/metrics/summary")
async def get_metrics_summary_endpoint(
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    group_by: Literal["stage", "model", "tool", "tenant"] = Query(default="stage"),
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return `percentile_cont` (`p50/p95/p99`) latency, token, and cost summary (`group_by=tenant` is admin-only)."""
    if group_by == "tenant" and user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant metrics summary (group_by=tenant) requires the 'admin' role.",
        )

    rec = get_telemetry_recorder()
    all_spans = list(rec.flushed_spans) + list(rec.queue)
    if from_ts:
        all_spans = [s for s in all_spans if s.started_at >= from_ts]
    if to_ts:
        all_spans = [s for s in all_spans if s.started_at <= to_ts]

    scope_tenant = None if group_by == "tenant" else tenant.tenant_id
    summary = summarize_spans_grouped(all_spans, tenant_id=scope_tenant, group_by=group_by)
    return {
        "tenant_id": tenant.tenant_id,
        "telemetry_health": rec.health_counters(),
        "summary": summary,
    }


@router.get("/api/v1/evals")
async def list_eval_reports_endpoint(
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return evaluation reports from `evals/reports/*.json` for the Quality & Guardrails UI."""
    reports_dir = find_repo_root() / "evals" / "reports"
    reports: list[dict[str, Any]] = []
    if reports_dir.is_dir():
        for p in sorted(reports_dir.glob("*.json")):
            try:
                reports.append({"filename": p.name, "report": json.loads(p.read_text(encoding="utf-8"))})
            except Exception:
                continue
    return {
        "tenant_id": tenant.tenant_id,
        "user_id": user.user_id,
        "report_count": len(reports),
        "reports": reports,
    }
