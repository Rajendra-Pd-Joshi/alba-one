"""Layer 7: Operational Guardrail (`guardrails/ops_layer.py`).

Enforces:
1. Global kill switch (`ops_kill_switch`, togglable via env or admin API).
2. Per-request token budget (`max_tokens_per_request`) and USD cost budget (`max_cost_usd_per_request`).
3. Per-tenant daily USD cost budget (`max_cost_usd_per_tenant_daily`).
4. Max LangGraph steps (`max_graph_steps`) and max MCP tool calls per hypothesis run (`max_tool_calls_per_run`).
5. Circuit breaker with automatic model fallback (`degraded_mode` / fallback model selection when consecutive upstream failures >= threshold).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alba_one.guardrails.types import GuardrailContext, GuardrailResult, build_guardrail_result


@dataclass
class OperationalGuardrailLimits:
    """Configurable operational limits loaded from `Settings`."""

    kill_switch: bool = False
    max_tokens_per_request: int = 32000
    max_cost_usd_per_request: float = 1.50
    max_cost_usd_per_tenant_daily: float = 250.00
    max_graph_steps: int = 15
    max_tool_calls_per_run: int = 10
    circuit_breaker_failure_threshold: int = 3
    fallback_model: str = "gpt-4o-mini-2024-07-18"


def check(
    payload: dict[str, Any],
    ctx: GuardrailContext,
    *,
    limits: OperationalGuardrailLimits | None = None,
) -> GuardrailResult:
    """Layer 7 `check(payload, ctx) -> GuardrailResult` for operational budgets, caps, and kill switch."""
    cfg = limits or OperationalGuardrailLimits()

    if cfg.kill_switch or bool(payload.get("kill_switch_override", False)):
        return build_guardrail_result(
            layer="ops",
            raw_action="block",
            policy="ops_kill_switch_active",
            ctx=ctx,
            details={"kill_switch": True},
            refusal_key="blocked_input",
        )

    tokens_used = int(payload.get("tokens_used", 0))
    if tokens_used > cfg.max_tokens_per_request:
        return build_guardrail_result(
            layer="ops",
            raw_action="block",
            policy="ops_request_token_budget_exceeded",
            ctx=ctx,
            details={"tokens_used": tokens_used, "max_tokens": cfg.max_tokens_per_request},
        )

    req_cost = float(payload.get("request_cost_usd", 0.0))
    if req_cost > cfg.max_cost_usd_per_request:
        return build_guardrail_result(
            layer="ops",
            raw_action="block",
            policy="ops_request_cost_budget_exceeded",
            ctx=ctx,
            details={"request_cost_usd": req_cost, "max_cost_usd": cfg.max_cost_usd_per_request},
        )

    tenant_daily_cost = float(payload.get("tenant_daily_cost_usd", 0.0))
    if tenant_daily_cost > cfg.max_cost_usd_per_tenant_daily:
        return build_guardrail_result(
            layer="ops",
            raw_action="block",
            policy="ops_tenant_daily_budget_exceeded",
            ctx=ctx,
            details={
                "tenant_daily_cost_usd": tenant_daily_cost,
                "max_daily_cost_usd": cfg.max_cost_usd_per_tenant_daily,
            },
        )

    graph_steps = int(payload.get("graph_steps", 0))
    if graph_steps > cfg.max_graph_steps:
        return build_guardrail_result(
            layer="ops",
            raw_action="block",
            policy="ops_max_graph_steps_exceeded",
            ctx=ctx,
            details={"graph_steps": graph_steps, "max_graph_steps": cfg.max_graph_steps},
        )

    tool_calls = int(payload.get("tool_calls_count", 0))
    if tool_calls > cfg.max_tool_calls_per_run:
        return build_guardrail_result(
            layer="ops",
            raw_action="block",
            policy="ops_max_tool_calls_exceeded",
            ctx=ctx,
            details={"tool_calls_count": tool_calls, "max_tool_calls": cfg.max_tool_calls_per_run},
        )

    consecutive_failures = int(payload.get("consecutive_llm_failures", 0))
    if consecutive_failures >= cfg.circuit_breaker_failure_threshold:
        return build_guardrail_result(
            layer="ops",
            raw_action="mask",
            policy="ops_circuit_breaker_fallback_activated",
            ctx=ctx,
            details={
                "degraded_mode": True,
                "consecutive_llm_failures": consecutive_failures,
                "routed_to_fallback_model": cfg.fallback_model,
            },
            sanitized_payload={"active_model": cfg.fallback_model, "degraded_mode": True},
        )

    return build_guardrail_result(
        layer="ops",
        raw_action="pass",
        policy="ops_within_budgets",
        ctx=ctx,
        details={
            "tokens_used": tokens_used,
            "request_cost_usd": req_cost,
            "graph_steps": graph_steps,
            "tool_calls_count": tool_calls,
        },
    )
