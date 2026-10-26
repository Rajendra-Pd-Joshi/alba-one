"""Phase 9 Operational Cost Evaluation (`evals/ops_cost_eval.py`).

Reads `SpanRecord` rows through `observability/queries.py` to report per-model and per-run
costs in USD and configured JPY (`fx_usdjpy`, `fx_rate_date`), `price_table_version`, and
`unpriced_calls: N`. Thresholds remain `TODO(owner)` in `evals/thresholds.yaml`.
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

from alba_one.observability.queries import aggregate_decision_run_metrics, summarize_spans_grouped
from evals.ops_latency_eval import build_sample_operational_spans


def evaluate_ops_cost() -> dict[str, Any]:
    rec = build_sample_operational_spans()
    by_model = summarize_spans_grouped(rec.flushed_spans, tenant_id="tenant_alba_demo", group_by="model")
    by_tool = summarize_spans_grouped(rec.flushed_spans, tenant_id="tenant_alba_demo", group_by="tool")
    sample_run = aggregate_decision_run_metrics(
        rec.flushed_spans,
        run_id="run_ops_01",
        decision_id="dec_ops_01",
        tenant_id="tenant_alba_demo",
    )
    return {
        "suite": "ops_cost_eval",
        "thresholds_status": "TODO(owner) in evals/thresholds.yaml",
        "price_table_version": by_model["price_table_version"],
        "fx_usdjpy": by_model["fx_usdjpy"],
        "fx_rate_date": by_model["fx_rate_date"],
        "unpriced_tool_calls": by_tool["unpriced_calls"],
        "sample_decision_run": sample_run.to_dict(),
        "by_model": by_model["groups"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 9 Operational Cost Eval")
    parser.parse_args(argv)
    print(json.dumps(evaluate_ops_cost(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
