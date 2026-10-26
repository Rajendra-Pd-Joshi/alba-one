"""Run all 22 MCP server evaluations (`evals/mcp/run_all.py`).

Usage:
  uv run python evals/mcp/run_all.py --allow-draft
  uv run python evals/mcp/run_all.py --allow-draft --smoke 4
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[2]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alba_one.mcp_servers.base import load_mcp_registry
from evals.mcp.engine import evaluate_server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all 22 ALBA ONE MCP server evaluations")
    parser.add_argument("--allow-draft", action="store_true", help="Allow status='draft' golden items")
    parser.add_argument("--smoke", type=int, default=None, help="Evaluate first N items per server")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    registry = load_mcp_registry()
    reports = []
    for server_name in registry:
        reports.append(evaluate_server(server_name, allow_draft=args.allow_draft, smoke_limit=args.smoke))

    if args.json:
        print(json.dumps({"server_count": len(reports), "reports": reports}, ensure_ascii=False, indent=2))
        return 0

    print(f"ALBA ONE — Evaluated {len(reports)} MCP servers (allow_draft={args.allow_draft}):")
    print(
        f"{'SERVER':<22} {'ITEMS':<6} {'JP/EN':<7} {'TOOL_ACC':<10} "
        f"{'ARG_ACC':<10} {'MCP_USE':<10} {'MULTI_TURN':<11} {'NEG_ABSTAIN'}"
    )
    print("-" * 98)
    for r in reports:
        m = r["metrics"]
        jp_en = f"{r['ja_items']}/{r['en_items']}"
        print(
            f"{r['mcp_server']:<22} {r['items_evaluated']:<6} {jp_en:<7} "
            f"{m['ToolCorrectnessMetric']:<10.4f} {m['ArgumentCorrectnessMetric']:<10.4f} "
            f"{m['MCPUseMetric']:<10.4f} {m['MultiTurnMCPUseMetric']:<11.4f} {m['NegativeAbstentionRate']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
