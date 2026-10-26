"""Thin MCP tool handlers wrapping deterministic domain calculators (`mcp_servers/calculator_handlers.py`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from alba_one.mcp_servers.delivery_planning.calculators.sla_and_cost import (
    calculate_route_cost_scenarios_jpy,
    calculate_sla_breach_probability,
)
from alba_one.mcp_servers.experiment_tracking.calculators.release_tradeoffs import (
    calculate_model_release_tradeoffs,
)
from alba_one.mcp_servers.staffing.calculators.overtime import calculate_overtime_margin
from alba_one.mcp_servers.vessel_allocation.calculators.berth import calculate_berth_ukc_margin


def handle_calc_sla_breach(args: dict[str, Any]) -> dict[str, Any]:
    res = calculate_sla_breach_probability(
        sla_limit_hours=float(args.get("sla_limit_hours", 6.0)),
        historical_transit_hours=[float(x) for x in args.get("historical_transit_hours", [5.1, 5.4, 5.8, 6.2, 5.5, 5.3, 6.4, 5.2, 5.6, 5.7])],
        planned_buffer_hours=float(args.get("planned_buffer_hours", 0.0)),
        min_sample_size=int(args.get("min_sample_size", 5)),
        seed=int(args.get("seed", 42)),
    )
    return res.to_dict()


def handle_calc_route_cost_jpy(args: dict[str, Any]) -> dict[str, Any]:
    res = calculate_route_cost_scenarios_jpy(
        distance_km=float(args.get("distance_km", 350.0)),
        base_rate_jpy_per_km=float(args.get("base_rate_jpy_per_km", 280.0)),
        reefer_surcharge_jpy=float(args.get("reefer_surcharge_jpy", 25000.0)),
        highway_toll_jpy=float(args.get("highway_toll_jpy", 18000.0)),
        currency=str(args.get("currency", "JPY")),
    )
    return res.to_dict()


def handle_calc_overtime_margin(args: dict[str, Any]) -> dict[str, Any]:
    verified_overrides = args.get("verified_overrides")
    res = calculate_overtime_margin(
        current_monthly_overtime_hours=float(args.get("current_monthly_overtime_hours", 38.5)),
        planned_additional_hours_base=float(args.get("planned_additional_hours_base", 4.0)),
        verified_overrides=verified_overrides if isinstance(verified_overrides, dict) else None,
    )
    return res.to_dict()


def handle_calc_berth_ukc(args: dict[str, Any]) -> dict[str, Any]:
    verified_overrides = args.get("verified_overrides")
    res = calculate_berth_ukc_margin(
        berth_depth_m=float(args.get("berth_depth_m", 14.5)),
        vessel_draft_m=float(args.get("vessel_draft_m", 12.8)),
        tide_offset_base_m=float(args.get("tide_offset_base_m", 0.2)),
        verified_overrides=verified_overrides if isinstance(verified_overrides, dict) else None,
    )
    return res.to_dict()


def handle_calc_release_tradeoffs(args: dict[str, Any]) -> dict[str, Any]:
    res = calculate_model_release_tradeoffs(
        metric_name=str(args.get("metric_name", "p95_latency_ms")),
        unit=str(args.get("unit", "ms")),
        baseline_runs=[float(x) for x in args.get("baseline_runs", [410.0, 415.0, 405.0, 420.0, 410.0])],
        candidate_runs=[float(x) for x in args.get("candidate_runs", [380.0, 385.0, 390.0, 382.0, 388.0])],
        min_runs_for_significance=int(args.get("min_runs_for_significance", 5)),
    )
    return res.to_dict()


CALCULATOR_TOOL_HANDLERS: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {
    ("delivery_planning", "calculate_sla_breach_probability"): handle_calc_sla_breach,
    ("delivery_planning", "calculate_route_cost_jpy"): handle_calc_route_cost_jpy,
    ("staffing", "calculate_overtime_margin"): handle_calc_overtime_margin,
    ("vessel_allocation", "calculate_berth_ukc_margin"): handle_calc_berth_ukc,
    ("experiment_tracking", "calculate_model_release_tradeoffs"): handle_calc_release_tradeoffs,
}
