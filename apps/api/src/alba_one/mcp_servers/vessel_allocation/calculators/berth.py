"""Berth Under-Keel Clearance (UKC) & Reefer Wait-Time Calculator (`vessel_allocation/calculators/berth.py`).

Per Phase 6 User Answer 3:
- Checks `port_berth_under_keel_clearance_min_m` in `config/regulatory_params.yaml` (`verified_by` gate).
- Computes net under-keel clearance (`berth_depth_m + tide_offset_m - vessel_draft_m`) and
  excess clearance above minimum safety threshold across `low` / `base` / `high` tide scenarios.
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


def calculate_berth_ukc_margin(
    *,
    berth_depth_m: float,
    vessel_draft_m: float,
    tide_offset_base_m: float = 0.0,
    tide_offset_low_m: float = -0.4,
    tide_offset_high_m: float = 0.5,
    param_key: str = "port_berth_under_keel_clearance_min_m",
    config_path: str | Path | None = None,
    verified_overrides: dict[str, str] | None = None,
) -> CalcResult:
    """Compute net Under-Keel Clearance (UKC) safety margin in meters gated on `verified_by`."""
    params = load_regulatory_params(config_path, verified_overrides=verified_overrides)
    is_verified, entry, err_msg = check_param_verified(param_key, params)

    inputs = {
        "berth_depth_m": berth_depth_m,
        "vessel_draft_m": vessel_draft_m,
        "tide_offset_base_m": tide_offset_base_m,
        "tide_offset_low_m": tide_offset_low_m,
        "tide_offset_high_m": tide_offset_high_m,
        "param_key": param_key,
    }
    if not is_verified or entry is None:
        return CalcResult(
            formula_id="vessel.berth_ukc_margin_m",
            version="1.0.0",
            status="parameters_not_verified",
            value=None,
            unit="meters",
            method="Gated on verified maritime safety parameter in config/regulatory_params.yaml",
            inputs=inputs,
            assumptions=["Safety threshold must be verified by Port Captain in config/regulatory_params.yaml."],
            warnings=[err_msg],
            disclaimer=LEGAL_DISCLAIMER_EN,
        )

    min_ukc = float(entry["value"])
    net_low = round((berth_depth_m + tide_offset_low_m) - vessel_draft_m - min_ukc, 3)
    net_base = round((berth_depth_m + tide_offset_base_m) - vessel_draft_m - min_ukc, 3)
    net_high = round((berth_depth_m + tide_offset_high_m) - vessel_draft_m - min_ukc, 3)

    scenarios = [
        ScenarioBound("low", f"low tide ({tide_offset_low_m:+.2f}m)", net_low, "meters"),
        ScenarioBound("base", f"mean tide ({tide_offset_base_m:+.2f}m)", net_base, "meters"),
        ScenarioBound("high", f"high tide ({tide_offset_high_m:+.2f}m)", net_high, "meters"),
    ]
    warnings: list[str] = []
    if net_low < 0:
        warnings.append(f"Low-tide UKC margin is negative ({net_low}m below {min_ukc}m requirement).")

    return CalcResult(
        formula_id="vessel.berth_ukc_margin_m",
        version="1.0.0",
        status="ok",
        value=net_base,
        unit="meters",
        method=f"(berth_depth_m + tide_offset_m) - vessel_draft_m - min_ukc ({min_ukc}m)",
        inputs={**inputs, "verified_min_ukc_m": min_ukc, "verified_by": entry["verified_by"]},
        assumptions=["Static draft measurement; wave squat requires separate dynamic allowance in high swell."],
        scenarios=scenarios,
        uncertainty_range=(net_low, net_high),
        warnings=warnings,
        disclaimer=LEGAL_DISCLAIMER_EN,
    )
