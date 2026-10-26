"""Cold-Chain Route SLA Breach Probability & Cost Scenario Calculator (`delivery_planning/calculators/sla_and_cost.py`).

Per Phase 6 User Answer 3:
- Empirical SLA breach probability with a seeded RNG (`random.Random(seed)`) for reproducible
  bootstrap uncertainty ranges.
- Returns `status="insufficient_data"` (with `value=None`) when `len(historical_transit_hours) < min_sample_size`.
- Returns a `low` / `base` / `high` sensitivity table for route cost in JPY (`convert_currency_jpy`).
"""

from __future__ import annotations

from collections.abc import Sequence
import random

from alba_one.mcp_servers.calculators_base import (
    LEGAL_DISCLAIMER_EN,
    CalcResult,
    ScenarioBound,
    convert_currency_jpy,
)


def calculate_sla_breach_probability(
    *,
    sla_limit_hours: float,
    historical_transit_hours: Sequence[float],
    planned_buffer_hours: float = 0.0,
    min_sample_size: int = 5,
    data_window: str = "2026-Q3 (90d)",
    seed: int = 42,
) -> CalcResult:
    """Compute empirical probability that `transit_hours - planned_buffer_hours > sla_limit_hours`."""
    n = len(historical_transit_hours)
    inputs = {
        "sla_limit_hours": sla_limit_hours,
        "historical_sample_count": n,
        "planned_buffer_hours": planned_buffer_hours,
        "min_sample_size": min_sample_size,
        "seed": seed,
    }
    if n < min_sample_size:
        return CalcResult(
            formula_id="delivery.sla_breach_empirical",
            version="1.0.0",
            status="insufficient_data",
            value=None,
            unit="probability",
            method="Empirical breach frequency with seeded bootstrap 90% interval",
            inputs=inputs,
            assumptions=["Requires at least min_sample_size historical observations."],
            data_window=data_window,
            sample_size=n,
            warnings=[
                f"Insufficient historical data: got {n} observations, need >= {min_sample_size}."
            ],
            disclaimer=LEGAL_DISCLAIMER_EN,
        )

    effective_limit = sla_limit_hours + planned_buffer_hours
    breaches = sum(1 for h in historical_transit_hours if h > effective_limit)
    base_prob = round(breaches / n, 4)

    # Low / Base / High buffer sensitivity (+/- 0.5h buffer)
    low_breaches = sum(1 for h in historical_transit_hours if h > (effective_limit + 0.5))
    high_breaches = sum(1 for h in historical_transit_hours if h > (effective_limit - 0.5))
    low_prob = round(low_breaches / n, 4)
    high_prob = round(high_breaches / n, 4)

    # Seeded bootstrap (200 resamples) for reproducible 5th–95th percentile interval
    rng = random.Random(seed)
    boot_rates: list[float] = []
    for _ in range(200):
        sample = [rng.choice(historical_transit_hours) for _ in range(n)]
        boot_rates.append(sum(1 for h in sample if h > effective_limit) / n)
    boot_rates.sort()
    ci_low = round(boot_rates[int(0.05 * len(boot_rates))], 4)
    ci_high = round(boot_rates[int(0.95 * len(boot_rates))], 4)

    scenarios = [
        ScenarioBound("low", f"optimistic (+0.5h buffer, limit={effective_limit + 0.5}h)", low_prob, "probability"),
        ScenarioBound("base", f"baseline (limit={effective_limit}h)", base_prob, "probability"),
        ScenarioBound("high", f"adverse (-0.5h buffer, limit={effective_limit - 0.5}h)", high_prob, "probability"),
    ]
    return CalcResult(
        formula_id="delivery.sla_breach_empirical",
        version="1.0.0",
        status="ok",
        value=base_prob,
        unit="probability",
        method="Empirical breach ratio (breaches / sample_size) with seeded 200-iteration bootstrap 90% CI",
        inputs=inputs,
        assumptions=[
            "Historical transit times are representative of current route conditions.",
            "Cold-chain reefer pre-cooling time is included in planned_buffer_hours.",
        ],
        scenarios=scenarios,
        data_window=data_window,
        sample_size=n,
        uncertainty_range=(ci_low, ci_high),
        warnings=[],
        disclaimer=LEGAL_DISCLAIMER_EN,
    )


def calculate_route_cost_scenarios_jpy(
    *,
    distance_km: float,
    base_rate_jpy_per_km: float,
    reefer_surcharge_jpy: float,
    highway_toll_jpy: float,
    fuel_multiplier_low: float = 0.92,
    fuel_multiplier_high: float = 1.15,
    currency: str = "JPY",
    fx_usdjpy: float = 151.45,
) -> CalcResult:
    """Compute total cold-chain delivery route cost in `JPY` across `low` / `base` / `high` fuel scenarios."""
    dist_cost_base = distance_km * base_rate_jpy_per_km
    total_base = convert_currency_jpy(dist_cost_base + reefer_surcharge_jpy + highway_toll_jpy, currency, fx_usdjpy)
    total_low = convert_currency_jpy(
        (dist_cost_base * fuel_multiplier_low) + reefer_surcharge_jpy + highway_toll_jpy,
        currency,
        fx_usdjpy,
    )
    total_high = convert_currency_jpy(
        (dist_cost_base * fuel_multiplier_high) + reefer_surcharge_jpy + highway_toll_jpy,
        currency,
        fx_usdjpy,
    )
    scenarios = [
        ScenarioBound("low", f"fuel_multiplier={fuel_multiplier_low}", total_low, "JPY"),
        ScenarioBound("base", "fuel_multiplier=1.00", total_base, "JPY"),
        ScenarioBound("high", f"fuel_multiplier={fuel_multiplier_high}", total_high, "JPY"),
    ]
    return CalcResult(
        formula_id="delivery.route_cost_jpy",
        version="1.0.0",
        status="ok",
        value=total_base,
        unit="JPY",
        method="distance_km * base_rate_jpy_per_km * fuel_multiplier + reefer_surcharge_jpy + highway_toll_jpy",
        inputs={
            "distance_km": distance_km,
            "base_rate_jpy_per_km": base_rate_jpy_per_km,
            "reefer_surcharge_jpy": reefer_surcharge_jpy,
            "highway_toll_jpy": highway_toll_jpy,
            "currency": currency,
        },
        assumptions=["Single 2-8C refrigerated truck dispatch without overnight layover."],
        scenarios=scenarios,
        uncertainty_range=(total_low, total_high),
        disclaimer=LEGAL_DISCLAIMER_EN,
    )
