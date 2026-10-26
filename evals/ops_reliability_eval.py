"""Phase 9 Operational Reliability Evaluation (`evals/ops_reliability_eval.py`).

Reports retry counts, cache hit ratio, telemetry queue health (`spans_dropped`,
`db_write_failures`, `langsmith_export_failures`), and error rates via `observability/queries.py`.
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
from evals.ops_latency_eval import build_sample_operational_spans


def evaluate_ops_reliability() -> dict[str, Any]:
    rec = build_sample_operational_spans()
    summary = summarize_spans_grouped(rec.flushed_spans, tenant_id="tenant_alba_demo", group_by="stage")
    total_calls = max(1, summary["total_spans"])
    total_retries = sum(g["retry_count"] for g in summary["groups"].values())
    total_cache_hits = sum(g["cache_hits"] for g in summary["groups"].values())
    total_errors = sum(g["error_count"] for g in summary["groups"].values())

    return {
        "suite": "ops_reliability_eval",
        "thresholds_status": "TODO(owner) in evals/thresholds.yaml",
        "total_spans": summary["total_spans"],
        "retry_rate": round(total_retries / total_calls, 4),
        "cache_hit_ratio": round(total_cache_hits / total_calls, 4),
        "error_rate": round(total_errors / total_calls, 4),
        "telemetry_health": rec.health_counters(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 9 Operational Reliability Eval")
    parser.parse_args(argv)
    print(json.dumps(evaluate_ops_reliability(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
