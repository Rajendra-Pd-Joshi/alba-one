"""Phase 9 Operational Latency Evaluation (`evals/ops_latency_eval.py`).

Reads raw `SpanRecord` rows through the shared `observability/queries.py` module (`compute_latency_percentiles`
and `summarize_spans_grouped`), computing exact `percentile_cont` (`p50/p95/p99`) per stage alongside
`sample_size`. Thresholds remain `TODO(owner)` in `evals/thresholds.yaml`.
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

from alba_one.observability.queries import summarize_spans_grouped
from alba_one.observability.telemetry import BoundedSpanTelemetryRecorder


def build_sample_operational_spans(recorder: BoundedSpanTelemetryRecorder | None = None) -> BoundedSpanTelemetryRecorder:
    """Populate a `BoundedSpanTelemetryRecorder` with representative multi-stage spans across 6 runs."""
    rec = recorder or BoundedSpanTelemetryRecorder()
    stage_samples = [
        ("retrieve", "mcp_tool", "knowledge_base.kb_search", "internal", [95.0, 110.0, 125.0, 140.0, 105.0, 180.0]),
        ("rerank", "rerank", "rerank-v4.0-pro", "cohere_direct", [60.0, 65.0, 72.0, 68.0, 75.0, 90.0]),
        ("tool_call", "mcp_tool", "delivery_planning.calculate_sla_breach_probability", "internal", [12.0, 15.0, 14.0, 11.0, 16.0, 19.0]),
        ("hypothesis", "llm", "gpt-4o-2024-08-06", "openai", [380.0, 410.0, 395.0, 440.0, 420.0, 510.0]),
        ("judge", "llm", "gpt-4o-2024-08-06", "openai", [340.0, 360.0, 355.0, 390.0, 370.0, 450.0]),
    ]
    for step, kind, name, prov, lats in stage_samples:
        for i, lat in enumerate(lats):
            rec.record_span(
                trace_id=f"tr_ops_{i + 1:02d}",
                tenant_id="tenant_alba_demo",
                decision_id=f"dec_ops_{i + 1:02d}",
                run_id=f"run_ops_{i + 1:02d}",
                phase_step=step,  # type: ignore[arg-type]
                kind=kind,  # type: ignore[arg-type]
                model_or_tool=name,
                provider=prov,
                latency_ms=lat,
                reported_tokens_in=1200 if kind == "llm" else 0,
                reported_tokens_out=400 if kind == "llm" else 0,
                retry_count=1 if (step == "hypothesis" and i == 5) else 0,
                cache_hit=(step == "retrieve" and i == 2),
            )
    rec.flush()
    return rec


def evaluate_ops_latency(*, min_samples: int = 5) -> dict[str, Any]:
    rec = build_sample_operational_spans()
    summary = summarize_spans_grouped(
        rec.flushed_spans,
        tenant_id="tenant_alba_demo",
        group_by="stage",
        min_samples_for_percentiles=min_samples,
    )
    return {
        "suite": "ops_latency_eval",
        "thresholds_status": "TODO(owner) in evals/thresholds.yaml",
        "summary": summary,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 9 Operational Latency Eval")
    parser.add_argument("--min-samples", type=int, default=5)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate_ops_latency(min_samples=args.min_samples), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
