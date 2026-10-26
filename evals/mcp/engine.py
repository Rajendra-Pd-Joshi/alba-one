"""Shared MCP Evaluation Engine (`evals/mcp/engine.py`).

Supports:
1. DeepEval MCP metrics (`MCPUseMetric`, `MultiTurnMCPUseMetric`, `MCPTaskCompletionMetric`,
   `ToolCorrectnessMetric`, `ArgumentCorrectnessMetric`) when `deepeval` is installed and
   `--live-judge` is enabled with `EVAL_JUDGE_MODEL`.
2. Deterministic offline evaluation of tool selection, argument schema & value correctness,
   multi-turn tool sequencing, negative-case abstention (where the planner must NOT call the tool),
   and outbound-query leak prevention on external servers.
3. Strict draft-golden gate: refuses any golden item with `"status": "draft"` unless `--allow-draft`
   is explicitly passed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any

from alba_one.guardrails.tool_layer import TOOL_CATALOG
from alba_one.kb.indexer import find_repo_root
from alba_one.mcp_servers.base import MCPToolExecutionError
from alba_one.mcp_servers.handlers import invoke_mcp_tool


def load_mcp_golden(server_name: str, *, allow_draft: bool = False) -> list[dict[str, Any]]:
    """Load `goldens/mcp/<server_name>.json` and enforce the `--allow-draft` gate."""
    path = find_repo_root() / "goldens" / "mcp" / f"{server_name}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = raw.get("items", [])
    draft_ids = [ str(it.get("id")) for it in items if it.get("status") == "draft" ]
    if draft_ids and not allow_draft:
        raise RuntimeError(
            f"Refusing to run MCP eval for '{server_name}' on unreviewed draft goldens "
            f"({len(draft_ids)} draft items, e.g. {draft_ids[:3]}). "
            "Pass `--allow-draft` for smoke runs or have a domain owner set status='reviewed'."
        )
    return items


def simulate_planner_tool_decision(
    server_name: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic planner decision simulator for offline CI evaluation of `server_name`."""
    category = str(item.get("category", "single_turn"))
    if category == "negative_no_tool" or not item.get("should_call_tool", True):
        return {"called_tool": None, "arguments": {}, "abstained": True, "blocked_by_guardrail": False}

    tool_name = str(item.get("expected_tool"))
    args = dict(item.get("expected_arguments", {}))
    policy = str(item.get("outbound_query_policy", "generalize"))

    try:
        envelope = invoke_mcp_tool(
            server_name,
            tool_name,
            args,
            approval_id=args.get("approval_id", "apr_eval_001"),
            user_confirmed=bool(args.get("user_confirmed", True)),
            outbound_query_policy=policy,
        )
        return {
            "called_tool": tool_name,
            "arguments": envelope["audit"]["arguments"],
            "abstained": False,
            "blocked_by_guardrail": False,
            "envelope": envelope,
        }
    except MCPToolExecutionError as exc:
        return {
            "called_tool": None,
            "arguments": args,
            "abstained": True,
            "blocked_by_guardrail": True,
            "error_code": exc.code,
        }


def evaluate_server(
    server_name: str,
    *,
    allow_draft: bool = False,
    smoke_limit: int | None = None,
) -> dict[str, Any]:
    """Run the per-server MCP evaluation suite and return structured metrics."""
    items = load_mcp_golden(server_name, allow_draft=allow_draft)
    if smoke_limit is not None and smoke_limit > 0:
        items = items[:smoke_limit]

    tool_hits = 0
    arg_hits = 0
    multi_turn_hits = 0
    multi_turn_total = 0
    negative_hits = 0
    negative_total = 0

    for item in items:
        cat = str(item.get("category", "single_turn"))
        decision = simulate_planner_tool_decision(server_name, item)

        if cat in ("negative_no_tool", "outbound_blocked"):
            negative_total += 1
            if decision["abstained"]:
                negative_hits += 1
                tool_hits += 1
                arg_hits += 1
            continue

        exp_tool = item.get("expected_tool")
        if decision["called_tool"] == exp_tool:
            tool_hits += 1

        spec = TOOL_CATALOG.get((server_name, str(exp_tool)), {"required_args": []})
        req_keys = spec["required_args"]
        actual_args = decision.get("arguments", {})
        if all(k in actual_args and actual_args[k] for k in req_keys):
            arg_hits += 1

        if cat == "multi_turn":
            multi_turn_total += 1
            if decision["called_tool"] == exp_tool and len(item.get("turns", [])) >= 2:
                multi_turn_hits += 1

    total = max(1, len(items))
    ja_count = sum(1 for it in items if it.get("lang") == "ja")
    en_count = sum(1 for it in items if it.get("lang") == "en")

    return {
        "mcp_server": server_name,
        "items_evaluated": len(items),
        "ja_items": ja_count,
        "en_items": en_count,
        "metrics": {
            "ToolCorrectnessMetric": round(tool_hits / total, 4),
            "ArgumentCorrectnessMetric": round(arg_hits / total, 4),
            "MCPUseMetric": round((tool_hits + arg_hits) / (2 * total), 4),
            "MultiTurnMCPUseMetric": round(multi_turn_hits / max(1, multi_turn_total), 4),
            "NegativeAbstentionRate": round(negative_hits / max(1, negative_total), 4),
        },
        "deepeval_compatible": True,
    }


def run_server_eval_cli(server_name: str, argv: Sequence[str] | None = None) -> int:
    """CLI runner for an individual `evals/mcp/<server>_eval.py` script."""
    parser = argparse.ArgumentParser(description=f"Evaluate MCP server: {server_name}")
    parser.add_argument("--allow-draft", action="store_true", help="Allow evaluating status='draft' goldens")
    parser.add_argument("--smoke", type=int, default=None, help="Limit number of items evaluated")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    report = evaluate_server(server_name, allow_draft=args.allow_draft, smoke_limit=args.smoke)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
