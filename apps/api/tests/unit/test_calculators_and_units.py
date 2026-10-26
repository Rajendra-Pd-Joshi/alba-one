"""Unit tests for Phase 6 Deterministic Calculators, Regulatory Params & Unit Helpers (`test_calculators_and_units.py`)."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.kb.indexer import find_repo_root
from alba_one.mcp_servers.calculators_base import (
    convert_containers_to_teu,
    convert_currency_jpy,
    convert_mass_tonnes,
    convert_speed_knots_to_kmh,
    to_asia_tokyo_iso,
)
from alba_one.mcp_servers.delivery_planning.calculators.sla_and_cost import (
    calculate_route_cost_scenarios_jpy,
    calculate_sla_breach_probability,
)
from alba_one.mcp_servers.experiment_tracking.calculators.release_tradeoffs import (
    calculate_model_release_tradeoffs,
)
from alba_one.mcp_servers.staffing.calculators.overtime import calculate_overtime_margin
from alba_one.mcp_servers.vessel_allocation.calculators.berth import calculate_berth_ukc_margin


class TestCalculatorsAndUnits(unittest.TestCase):
    """Verify all deterministic calculators against `goldens/calculators.json` and unit conversions."""

    def test_all_golden_calculator_cases_match_hand_computed_values(self) -> None:
        golden_path = find_repo_root() / "goldens" / "calculators.json"
        raw = json.loads(golden_path.read_text(encoding="utf-8"))
        items = raw["items"]
        self.assertEqual(len(items), 8)

        for item in items:
            calc_name = item["calculator"]
            inp = item["inputs"]
            exp = item["expected"]

            if calc_name == "delivery.sla_breach_empirical":
                res = calculate_sla_breach_probability(**inp)
            elif calc_name == "delivery.route_cost_jpy":
                res = calculate_route_cost_scenarios_jpy(**inp)
            elif calc_name == "staffing.article36_overtime_margin":
                res = calculate_overtime_margin(**inp)
            elif calc_name == "vessel.berth_ukc_margin_m":
                res = calculate_berth_ukc_margin(**inp)
            elif calc_name == "experiment.model_release_delta":
                res = calculate_model_release_tradeoffs(**inp)
            else:
                self.fail(f"Unknown calculator {calc_name}")

            self.assertEqual(res.status, exp["status"], f"Status mismatch in {item['id']}")
            self.assertEqual(res.value, exp["value"], f"Value mismatch in {item['id']}")
            self.assertEqual(res.unit, exp["unit"], f"Unit mismatch in {item['id']}")

            if "scenarios" in exp:
                scen_map = {s.scenario: s.value for s in res.scenarios}
                self.assertEqual(scen_map, exp["scenarios"], f"Scenario mismatch in {item['id']}")
            if "warning_substring" in exp:
                self.assertTrue(
                    any(exp["warning_substring"] in w for w in res.warnings),
                    f"Expected warning '{exp['warning_substring']}' in {res.warnings}",
                )

    def test_unit_and_locale_conversion_helpers(self) -> None:
        self.assertEqual(convert_currency_jpy(1000.0, "JPY"), 1000.0)
        self.assertEqual(convert_currency_jpy(100.0, "USD", fx_usdjpy=150.0), 15000.0)
        self.assertEqual(convert_mass_tonnes(2500.0, "kg"), 2.5)
        self.assertEqual(convert_containers_to_teu(12, "FEU"), 24.0)
        self.assertEqual(convert_speed_knots_to_kmh(10.0), 18.52)
        jst_iso = to_asia_tokyo_iso("2026-10-24T00:00:00Z")
        self.assertTrue(jst_iso.endswith("+09:00"))
        self.assertIn("T09:00:00", jst_iso)


if __name__ == "__main__":
    unittest.main()
