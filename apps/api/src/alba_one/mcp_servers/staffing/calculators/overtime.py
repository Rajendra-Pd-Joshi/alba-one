"""Article 36 Overtime Margin Calculator (`staffing/calculators/overtime.py`).

Per Phase 6 User Answer 3:
- Never hardcodes any legal limit from memory; reads `jp_labor_article36_monthly_overtime_hours`
  from `config/regulatory_params.yaml`.
- Refuses to compute (`status="parameters_not_verified"`, `value=None`) until `verified_by`
  is filled in by HR/legal counsel.
- Labels all outputs as `"Decision support only, not legal or safety advice; requires HR, legal, or safety owner review."`
"""

from __future__ import annotations

from pathlib import Path

from alba_one.mcp_servers.calculators_base import (
    LEGAL_DISCLAIMER_EN,
    CalcResult,
    ScenarioBound,
    check_param_verified,
    load_regulatory_params,
)


def calculate_overtime_margin(
    *,
    current_monthly_overtime_hours: float,
    planned_additional_hours_base: float,
    planned_additional_hours_low: float | None = None,
    planned_additional_hours_high: float | None = None,
    param_key: str = "jp_labor_article36_monthly_overtime_hours",
    config_path: str | Path | None = None,
    verified_overrides: dict[str, str] | None = None,
) -> CalcResult:
    """Compute remaining monthly overtime margin (`cap - (current + planned)`) gated on `verified_by`."""
    params = load_regulatory_params(config_path, verified_overrides=verified_overrides)
    is_verified, entry, err_msg = check_param_verified(param_key, params)

    low_add = planned_additional_hours_low if planned_additional_hours_low is not None else max(0.0, planned_additional_hours_base - 1.5)
    high_add = planned_additional_hours_high if planned_additional_hours_high is not None else planned_additional_hours_base + 2.5

    inputs = {
        "current_monthly_overtime_hours": current_monthly_overtime_hours,
        "planned_additional_hours_base": planned_additional_hours_base,
        "planned_additional_hours_low": low_add,
        "planned_additional_hours_high": high_add,
        "param_key": param_key,
    }

    if not is_verified or entry is None:
        return CalcResult(
            formula_id="staffing.article36_overtime_margin",
            version="1.0.0",
            status="parameters_not_verified",
            value=None,
            unit="hours/month",
            method="Gated on verified regulatory parameter in config/regulatory_params.yaml",
            inputs=inputs,
            assumptions=["Legal cap must be verified by HR/Legal in config/regulatory_params.yaml before execution."],
            warnings=[err_msg],
            disclaimer=LEGAL_DISCLAIMER_EN,
        )

    cap = float(entry["value"])
    margin_From_low = round(cap - (current_monthly_overtime_hours + low_add), 2)
    margin_base = round(cap - (current_monthly_overtime_hours + planned_additional_hours_base), 2)
    margin_From_high = round(cap - (current_monthly_overtime_hours + high_add), 2)

    # Note: in scenario table, "low" margin is the adverse/high-workload case, "high" margin is optimistic
    scenarios = [
        ScenarioBound("low", f"adverse shift extension (+{high_add}h)", margin_From_high, "hours/month"),
        ScenarioBound("base", f"planned shift (+{planned_additional_hours_base}h)", margin_base, "hours/month"),
        ScenarioBound("high", f"optimistic shift (+{low_add}h)", margin_From_low, "hours/month"),
    ]
    warnings: list[str] = []
    if margin_From_high < 0:
        warnings.append(
            f"Adverse scenario exceeds {param_key} cap ({cap}h) by {abs(margin_From_high):.2f}h."
        )

    return CalcResult(
        formula_id="staffing.article36_overtime_margin",
        version="1.0.0",
        status="ok",
        value=margin_base,
        unit="hours/month",
        method=f"cap ({cap}h from {param_key}, verified_by={entry['verified_by']}) - (current_monthly_overtime_hours + planned_additional_hours)",
        inputs={**inputs, "verified_cap_hours": cap, "verified_by": entry["verified_by"]},
        assumptions=[
            f"Uses parameter '{param_key}' effective {entry.get('effective_date')} ({entry.get('source')}).",
            "Excludes special-clause (特別条項) exemptions unless separately verified.",
        ],
        scenarios=scenarios,
        uncertainty_range=(margin_From_high, margin_From_low),
        warnings=warnings,
        disclaimer=LEGAL_DISCLAIMER_EN,
    )
