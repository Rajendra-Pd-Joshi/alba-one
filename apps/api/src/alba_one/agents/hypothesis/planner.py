"""Two-Round Shared Tool-Gathering & Counter-Evidence Planner (`agents/hypothesis/planner.py`).

Per Phase 6 User Answer 1:
- Flow: Round 1 (plan-driven broad gathering) -> draft hypotheses & gap check ->
  Round 2 (targeted gap-filling, including at least one query designed to find
  COUNTER-EVIDENCE for the leading hypothesis). No more than 2 rounds.
- Budgets from config (`MAX_TOOL_CALLS_PER_RUN`, `ROUND1_MAX_CALLS`, `ROUND2_MAX_CALLS`,
  `TOOL_TIMEOUT_SECONDS`, `MAX_RUN_COST`). When a budget is hit, stop gathering,
  record `budget_exhausted=True`, and continue to synthesis with what exists.
- Independent calls within a round run in parallel (`asyncio.gather`) with per-call
  timeouts; identical calls are de-duplicated within a run; failed calls become
  explicit `GapRecord` entries in `ledger.gaps`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.mcp_servers.handlers import invoke_mcp_tool


@dataclass(frozen=True)
class HypothesisGatheringBudgets:
    """Configurable budgets governing the 2-round tool-gathering step."""

    max_options: int = 4
    max_tool_calls_per_run: int = 10
    round1_max_calls: int = 6
    round2_max_calls: int = 4
    tool_timeout_seconds: float = 10.0
    max_run_cost: float = 0.50


@dataclass(frozen=True)
class PlannedToolCall:
    """Single planned MCP tool or calculator invocation in Round 1 or Round 2."""

    mcp_server: str
    tool_name: str
    arguments: dict[str, Any]
    is_counter_evidence_query: bool = False
    estimated_cost_usd: float = 0.01


def build_round1_plan(question: str, *, tenant_id: str, lang: str = "ja") -> list[PlannedToolCall]:
    """Build Round 1 broad tool & calculator gathering plan based on the decision workflow."""
    q_low = question.lower()
    calls: list[PlannedToolCall] = [
        PlannedToolCall(
            "knowledge_base",
            "kb_search",
            {"tenant_id": tenant_id, "query": question, "lang": lang, "top_k": 3},
        ),
        PlannedToolCall(
            "decision_history",
            "search_similar_decisions",
            {"tenant_id": tenant_id, "query": question, "lang": lang},
        ),
    ]
    if any(k in q_low for k in ("release", "model", "v2.4", "neptune", "モデル", "リリース")):
        calls.extend(
            [
                PlannedToolCall(
                    "experiment_tracking",
                    "compare_runs",
                    {"tenant_id": tenant_id, "baseline_id": "exp_neptune_v23", "candidate_id": "exp_neptune_v24", "lang": lang},
                ),
                PlannedToolCall(
                    "experiment_tracking",
                    "calculate_model_release_tradeoffs",
                    {"tenant_id": tenant_id, "metric_name": "p95_latency_ms", "unit": "ms", "lang": lang},
                ),
                PlannedToolCall(
                    "benchmark_registry",
                    "compare_regressions",
                    {"tenant_id": tenant_id, "baseline_tag": "ALBA-NEPTUNE-V2.3", "candidate_tag": "ALBA-NEPTUNE-V2.4", "lang": lang},
                ),
                PlannedToolCall(
                    "deployment_status",
                    "get_environment_status",
                    {"tenant_id": tenant_id, "environment": "production", "lang": lang},
                ),
            ]
        )
    else:
        calls.extend(
            [
                PlannedToolCall(
                    "delivery_planning",
                    "calculate_sla_breach_probability",
                    {"tenant_id": tenant_id, "sla_limit_hours": 6.0, "lang": lang},
                ),
                PlannedToolCall(
                    "delivery_planning",
                    "calculate_route_cost_jpy",
                    {"tenant_id": tenant_id, "distance_km": 350.0, "lang": lang},
                ),
                PlannedToolCall(
                    "staffing",
                    "calculate_overtime_margin",
                    {"tenant_id": tenant_id, "current_monthly_overtime_hours": 38.5, "lang": lang},
                ),
                PlannedToolCall(
                    "vessel_allocation",
                    "calculate_berth_ukc_margin",
                    {"tenant_id": tenant_id, "berth_depth_m": 14.5, "vessel_draft_m": 12.8, "lang": lang},
                ),
            ]
        )
    return calls


def build_round2_plan(
    question: str,
    ledger: EvidenceLedger,
    *,
    tenant_id: str,
    lang: str = "ja",
) -> list[PlannedToolCall]:
    """Build Round 2 gap-filling plan, ALWAYS including >=1 counter-evidence query for the leading hypothesis."""
    q_low = question.lower()
    calls: list[PlannedToolCall] = []

    if any(k in q_low for k in ("release", "model", "v2.4", "neptune", "モデル", "リリース")):
        # Mandatory counter-evidence query challenging the leading "release v2.4" hypothesis
        calls.append(
            PlannedToolCall(
                "model_benchmarks",
                "lookup_public_benchmarks",
                {
                    "tenant_id": tenant_id,
                    "query": (
                        "ALBA-NEPTUNE zero-shot evaluation caveats and out-of-distribution failure modes"
                        if lang == "en"
                        else "公開リーダーボード評価の限界と分布外データにおける精度低下リスク"
                    ),
                    "lang": lang,
                },
                is_counter_evidence_query=True,
            )
        )
        calls.append(
            PlannedToolCall(
                "experiment_tracking",
                "get_release_readiness_summary",
                {"tenant_id": tenant_id, "version_tag": "ALBA-NEPTUNE-V2.4", "lang": lang},
                is_counter_evidence_query=False,
            )
        )
    else:
        # Mandatory counter-evidence query challenging the leading route/berth hypothesis (e.g. gust wind suspension risk)
        calls.append(
            PlannedToolCall(
                "weather_marine",
                "get_port_weather",
                {"tenant_id": tenant_id, "port_code": "YOK", "lang": lang},
                is_counter_evidence_query=True,
            )
        )
        calls.append(
            PlannedToolCall(
                "regulatory_jp",
                "lookup_jp_regulation",
                {
                    "tenant_id": tenant_id,
                    "topic": "労働基準法第36条 時間外労働上限 医薬品GDP",
                    "lang": lang,
                },
                is_counter_evidence_query=False,
            )
        )
    return calls


async def execute_gathering_round(
    round_num: int,
    planned_calls: list[PlannedToolCall],
    ledger: EvidenceLedger,
    budgets: HypothesisGatheringBudgets,
    *,
    tool_executor: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> list[str]:
    """Execute one round of tool calls in parallel (`asyncio.gather`) with dedup, timeouts, and budget caps."""
    round_cap = budgets.round1_max_calls if round_num == 1 else budgets.round2_max_calls
    executable: list[PlannedToolCall] = []
    seen_in_round: set[str] = set()

    for call in planned_calls:
        # 1. Deduplicate identical calls within the run (and within the current batch) before charging budgets
        ckey = ledger.canonical_call_key(call.mcp_server, call.tool_name, call.arguments)
        if ckey in seen_in_round or ledger.find_cached_call(call.mcp_server, call.tool_name, call.arguments) is not None:
            continue
        seen_in_round.add(ckey)

        # 2. Enforce round cap, total call cap, and cost budget
        round_used = ledger.round1_calls if round_num == 1 else ledger.round2_calls
        if round_used >= round_cap:
            ledger.budget_exhausted = True
            ledger.budget_exhausted_reason = f"round{round_num}_max_calls ({round_cap}) reached"
            break
        if ledger.total_tool_calls >= budgets.max_tool_calls_per_run:
            ledger.budget_exhausted = True
            ledger.budget_exhausted_reason = (
                f"max_tool_calls_per_run ({budgets.max_tool_calls_per_run}) reached"
            )
            break
        if ledger.accumulated_cost_usd + call.estimated_cost_usd > budgets.max_run_cost:
            ledger.budget_exhausted = True
            ledger.budget_exhausted_reason = f"max_run_cost (${budgets.max_run_cost:.2f}) reached"
            break

        executable.append(call)
        ledger.total_tool_calls += 1
        if round_num == 1:
            ledger.round1_calls += 1
        else:
            ledger.round2_calls += 1
        ledger.accumulated_cost_usd = round(ledger.accumulated_cost_usd + call.estimated_cost_usd, 4)

    exec_fn = tool_executor or (lambda s, t, a: invoke_mcp_tool(s, t, a))

    async def _run_one(c: PlannedToolCall) -> tuple[PlannedToolCall, dict[str, Any] | None, str | None]:
        try:
            res = await asyncio.wait_for(
                asyncio.to_thread(exec_fn, c.mcp_server, c.tool_name, c.arguments),
                timeout=budgets.tool_timeout_seconds,
            )
            return c, res, None
        except asyncio.TimeoutError:
            return c, None, f"Timed out after {budgets.tool_timeout_seconds}s"
        except Exception as exc:
            return c, None, f"{type(exc).__name__}: {exc}"

    results = await asyncio.gather(*(_run_one(c) for c in executable))
    new_ids: list[str] = []
    for c, env, err in results:
        if err is not None or env is None:
            ledger.record_gap(
                round_num=round_num,
                mcp_server=c.mcp_server,
                tool_name=c.tool_name,
                reason=err or "Unknown tool execution failure",
                is_counter_evidence_query=c.is_counter_evidence_query,
            )
        else:
            item = ledger.add_mcp_envelope(env, arguments=c.arguments)
            new_ids.append(item.evidence_id)
    return new_ids
