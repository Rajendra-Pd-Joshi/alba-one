"""Shared Observability Query & `percentile_cont` Aggregation Engine (`observability/queries.py`).

Used by BOTH `/api/v1/metrics/...` (`api/metrics.py`) AND `evals/ops_*_eval.py` so the
Quality UI and offline ops evaluations can never disagree.

Per Phase 9 User Answer 1:
- Percentiles (`p50`, `p95`, `p99`) are computed from raw span rows using exact continuous
  linear interpolation (`percentile_cont`), NEVER averages of averages!
- Returns `sample_size` with every percentile and reports `status="insufficient_samples"`
  (`p50=None, p95=None, p99=None`) below `min_samples_for_percentiles` (default 5, `TODO(owner)`).
- Aggregates `DecisionRunMetrics` per decision run, including `unpriced_calls`, `retry_count`,
  `cache_hit_ratio`, and `budget_exhausted`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import math
from typing import Any, Literal

from alba_one.observability.cost import PriceTableConfig, convert_usd_to_configured_jpy, load_price_table
from alba_one.observability.spans import SpanRecord


def compute_percentile_cont(values: Sequence[float], p: float) -> float:
    """Exact continuous percentile matching PostgreSQL `percentile_cont(p) WITHIN GROUP (ORDER BY x)`."""
    if not values:
        raise ValueError("Cannot compute percentile_cont of empty sequence.")
    if p <= 0.0:
        return round(float(min(values)), 4)
    if p >= 1.0:
        return round(float(max(values)), 4)
    sorted_vals = sorted(float(x) for x in values)
    n = len(sorted_vals)
    if n == 1:
        return round(sorted_vals[0], 4)
    pos = p * (n - 1)
    lower_idx = int(math.floor(pos))
    upper_idx = int(math.ceil(pos))
    if lower_idx == upper_idx:
        return round(sorted_vals[lower_idx], 4)
    weight = pos - lower_idx
    interpolated = sorted_vals[lower_idx] + weight * (sorted_vals[upper_idx] - sorted_vals[lower_idx])
    return round(interpolated, 4)


def compute_latency_percentiles(
    latencies_ms: Sequence[float],
    *,
    min_samples: int = 5,  # TODO(owner): tune minimum sample threshold
) -> dict[str, Any]:
    """Compute `(p50, p95, p99)` from raw span rows, returning `insufficient_samples` below `min_samples`."""
    n = len(latencies_ms)
    if n < min_samples:
        return {
            "status": "insufficient_samples",
            "message": "insufficient samples",
            "sample_size": n,
            "min_samples": min_samples,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }
    return {
        "status": "ok",
        "sample_size": n,
        "min_samples": min_samples,
        "p50_ms": compute_percentile_cont(latencies_ms, 0.50),
        "p95_ms": compute_percentile_cont(latencies_ms, 0.95),
        "p99_ms": compute_percentile_cont(latencies_ms, 0.99),
    }


@dataclass(frozen=True)
class DecisionRunMetrics:
    """Aggregated operational metrics for a single decision run (`decision_run_metrics` table)."""

    run_id: str
    decision_id: str
    tenant_id: str
    total_latency_ms: float
    per_stage_latency_ms: dict[str, float]
    tokens_in: int
    tokens_out: int
    total_cost_usd: float | None
    total_cost_jpy: float | None
    fx_usdjpy: float
    fx_rate_date: str
    unpriced_calls: int
    tool_call_count: int
    retry_count: int
    guardrail_event_counts: dict[str, int]
    cache_hit_ratio: float
    budget_exhausted: bool
    span_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_decision_run_metrics(
    spans: Sequence[SpanRecord],
    *,
    run_id: str,
    decision_id: str,
    tenant_id: str,
    budget_exhausted: bool = False,
    price_table: PriceTableConfig | None = None,
) -> DecisionRunMetrics:
    """Aggregate raw `SpanRecord` rows for `(tenant_id, decision_id, run_id)`."""
    pt = price_table or load_price_table()
    run_spans = [s for s in spans if s.tenant_id == tenant_id and (s.run_id == run_id or s.decision_id == decision_id)]

    per_stage: dict[str, float] = {}
    tok_in = 0
    tok_out = 0
    priced_sum = 0.0
    has_priced = False
    unpriced = 0
    tool_calls = 0
    retries = 0
    cache_hits = 0
    gr_counts: dict[str, int] = {"pass": 0, "blocked": 0, "error": 0}

    for s in run_spans:
        per_stage[s.phase_step] = round(per_stage.get(s.phase_step, 0.0) + s.latency_ms, 2)
        tok_in += s.tokens_in
        tok_out += s.tokens_out
        retries += s.retry_count
        if s.cache_hit or s.status == "cache_hit":
            cache_hits += 1
        if s.kind == "mcp_tool":
            tool_calls += 1
        if s.kind == "guardrail":
            key = "blocked" if s.status == "blocked" else ("error" if s.status == "error" else "pass")
            gr_counts[key] = gr_counts.get(key, 0) + 1
        if s.cost_amount is None:
            unpriced += 1
        else:
            priced_sum += s.cost_amount
            has_priced = True

    total_lat = round(sum(s.latency_ms for s in run_spans), 2)
    cost_usd = round(priced_sum, 6) if has_priced else (0.0 if not run_spans else None)
    jpy_info = convert_usd_to_configured_jpy(cost_usd, price_table=pt)
    n_spans = len(run_spans)

    return DecisionRunMetrics(
        run_id=run_id,
        decision_id=decision_id,
        tenant_id=tenant_id,
        total_latency_ms=total_lat,
        per_stage_latency_ms=per_stage,
        tokens_in=tok_in,
        tokens_out=tok_out,
        total_cost_usd=jpy_info["cost_usd"],
        total_cost_jpy=jpy_info["cost_jpy"],
        fx_usdjpy=jpy_info["fx_usdjpy"],
        fx_rate_date=jpy_info["fx_rate_date"],
        unpriced_calls=unpriced,
        tool_call_count=tool_calls,
        retry_count=retries,
        guardrail_event_counts=gr_counts,
        cache_hit_ratio=round(cache_hits / max(1, n_spans), 4),
        budget_exhausted=budget_exhausted,
        span_count=n_spans,
    )


def summarize_spans_grouped(
    spans: Sequence[SpanRecord],
    *,
    tenant_id: str | None,
    group_by: Literal["stage", "model", "tool", "tenant"] = "stage",
    min_samples_for_percentiles: int = 5,
    price_table: PriceTableConfig | None = None,
) -> dict[str, Any]:
    """Summarize raw spans grouped by `stage | model | tool | tenant` using exact `percentile_cont`."""
    pt = price_table or load_price_table()
    filtered = [s for s in spans if (tenant_id is None or s.tenant_id == tenant_id)]

    buckets: dict[str, list[SpanRecord]] = {}
    for s in filtered:
        if group_by == "stage":
            key = s.phase_step
        elif group_by == "model":
            if s.kind not in ("llm", "embedding", "rerank"):
                continue
            key = s.model_or_tool
        elif group_by == "tool":
            if s.kind not in ("mcp_tool", "calc"):
                continue
            key = s.model_or_tool
        else:
            key = s.tenant_id
        buckets.setdefault(key, []).append(s)

    groups_out: dict[str, Any] = {}
    total_unpriced = 0
    for key, group_spans in sorted(buckets.items()):
        lats = [s.latency_ms for s in group_spans]
        unp = sum(1 for s in group_spans if s.cost_amount is None)
        total_unpriced += unp
        priced = [s.cost_amount for s in group_spans if s.cost_amount is not None]
        usd_sum = round(sum(priced), 6) if priced else None
        jpy_info = convert_usd_to_configured_jpy(usd_sum, price_table=pt)
        groups_out[key] = {
            "call_count": len(group_spans),
            "latency": compute_latency_percentiles(lats, min_samples=min_samples_for_percentiles),
            "tokens_in": sum(s.tokens_in for s in group_spans),
            "tokens_out": sum(s.tokens_out for s in group_spans),
            "cost_usd": jpy_info["cost_usd"],
            "cost_jpy": jpy_info["cost_jpy"],
            "unpriced_calls": unp,
            "retry_count": sum(s.retry_count for s in group_spans),
            "cache_hits": sum(1 for s in group_spans if s.cache_hit),
            "error_count": sum(1 for s in group_spans if s.status in ("error", "timeout")),
        }

    return {
        "group_by": group_by,
        "total_spans": len(filtered),
        "unpriced_calls": total_unpriced,
        "fx_usdjpy": pt.fx_usdjpy,
        "fx_rate_date": pt.fx_rate_date,
        "price_table_version": pt.price_table_version,
        "groups": groups_out,
    }
