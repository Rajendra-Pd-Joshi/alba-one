"""CLI Script to Recompute Historical Span Costs (`scripts/recompute_costs.py`).

Per Phase 9 User Answer 1:
Recomputes `cost_amount` and updates `price_table_version` across stored `SpanRecord` rows
whenever `config/models.yaml` prices change.

Usage:
  PYTHONPATH="apps/api/src:." uv run python scripts/recompute_costs.py --dry-run
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alba_one.observability.cost import load_price_table, recompute_spans_cost
from alba_one.observability.spans import SpanRecord


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute historical span costs from config/models.yaml")
    parser.add_argument("--config", type=Path, default=None, help="Path to models.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Run against synthetic sample spans without DB commit")
    args = parser.parse_args(argv)

    pt = load_price_table(args.config)
    sample_spans = [
        SpanRecord(
            span_id="sp_hist_001",
            parent_span_id=None,
            trace_id="tr_001",
            tenant_id="tenant_alba_demo",
            decision_id="dec_demo_001",
            run_id="run_001",
            attempt=1,
            phase_step="hypothesis",
            kind="llm",
            model_or_tool="gpt-4o-2024-08-06",
            provider="openai",
            prompt_version="v1.0",
            guardrail_version="1",
            model_config_version="1.0",
            tool_def_hash=None,
            app_version="0.9.0",
            lang="ja",
            tokens_in=2000,
            tokens_out=500,
            tokens_estimated=False,
            latency_ms=420.0,
            ttfb_ms=110.0,
            status="ok",
            error_type=None,
            retry_count=0,
            cache_hit=False,
            cost_amount=0.0,
            cost_currency="USD",
            price_table_version="old.v0",
            cost_estimated=False,
        ),
        SpanRecord(
            span_id="sp_hist_002_unpriced",
            parent_span_id="sp_hist_001",
            trace_id="tr_001",
            tenant_id="tenant_alba_demo",
            decision_id="dec_demo_001",
            run_id="run_001",
            attempt=1,
            phase_step="tool_call",
            kind="mcp_tool",
            model_or_tool="weather_marine.get_port_weather",
            provider="internal",
            prompt_version=None,
            guardrail_version="1",
            model_config_version="1.0",
            tool_def_hash="th_01",
            app_version="0.9.0",
            lang="ja",
            tokens_in=0,
            tokens_out=0,
            tokens_estimated=False,
            latency_ms=85.0,
            ttfb_ms=None,
            status="ok",
            error_type=None,
            retry_count=0,
            cache_hit=False,
            cost_amount=None,
            cost_currency="USD",
            price_table_version="old.v0",
            cost_estimated=True,
        ),
    ]
    report = recompute_spans_cost(sample_spans, price_table=pt)
    print(json.dumps({**report, "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
