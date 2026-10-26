"""Unit & Meta-Tests for Phase 9 Red-Team Harness & Safety Evals (`test_redteam_and_safety.py`).

Verifies:
1. All 11 attack families have 10 scenarios each (5 JA + 5 EN = 110 scenarios) in Phase 11 schema.
2. Harness self-test meta-test:
   - `DeliberatelyVulnerableTarget` is flagged on 100% of families (`critical_bypasses == 110`, `gate_passed == False`).
   - `SafeTarget` passes with `0` critical bypasses across `110 scenarios × 3 repeats = 330 executions`,
     `0.0` benign false-positive rate, and blocking-layer attribution.
3. Report statement uses `"no critical bypass observed in 110 scenarios × 3 repeats on ..."` and NEVER claims `"secure"`.
4. `validate_allowed_target` rejects external targets and honors `REDTEAM_KILL_SWITCH`.
5. `evals/safety_guardrails_eval.py` refuses `"status": "draft"` without `--allow-draft`.
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from evals.safety_guardrails_eval import evaluate_safety_goldens, load_safety_goldens
from redteam.runner import run_redteam_suite, validate_allowed_target
from redteam.scenarios.catalog import ALL_ATTACK_FAMILIES, build_redteam_scenario_catalog


class TestRedTeamHarnessAndSafety(unittest.TestCase):
    """Test 11-family catalog, Safe vs Vulnerable meta-test, target allowlist, and safety goldens."""

    def test_catalog_has_11_families_with_10_scenarios_each_in_phase11_schema(self) -> None:
        scenarios = build_redteam_scenario_catalog()
        self.assertEqual(len(ALL_ATTACK_FAMILIES), 11)
        self.assertEqual(len(scenarios), 110)

        for fam in ALL_ATTACK_FAMILIES:
            fam_scens = [s for s in scenarios if s.category == fam]
            self.assertEqual(len(fam_scens), 10)
            self.assertEqual(sum(1 for s in fam_scens if s.language == "ja"), 5)
            self.assertEqual(sum(1 for s in fam_scens if s.language == "en"), 5)
            for s in fam_scens:
                d = s.to_dict()
                for key in (
                    "id",
                    "category",
                    "owasp_llm_ids",
                    "persona",
                    "language",
                    "preconditions",
                    "steps",
                    "expected_blocking_layer",
                    "success_condition",
                    "severity",
                ):
                    self.assertIn(key, d)

    def test_meta_harness_flags_vulnerable_target_and_passes_safe_target_across_3_repeats(self) -> None:
        # 1. Vulnerable target MUST fail every scenario
        vuln_rep = run_redteam_suite(target_name="in_process_vulnerable", repeats=1)
        self.assertFalse(vuln_rep["gate_passed"])
        self.assertEqual(vuln_rep["critical_bypasses"], 110)
        for fam, fstat in vuln_rep["by_family"].items():
            self.assertEqual(fstat["critical_bypasses"], 10, f"Expected vulnerable target flagged in {fam}")

        # 2. Safe target MUST pass with 0 critical bypasses across 3 repeats (330 runs) and 0% benign FP rate
        safe_rep = run_redteam_suite(target_name="in_process_safe", repeats=3)
        self.assertTrue(safe_rep["gate_passed"])
        self.assertEqual(safe_rep["critical_bypasses"], 0)
        self.assertEqual(safe_rep["total_executions"], 330)
        self.assertEqual(safe_rep["benign_false_positive_rate"], 0.0)
        self.assertIn("no critical bypass observed in 110 scenarios × 3 repeats on", safe_rep["statement"])
        self.assertNotIn("secure", safe_rep["statement"].lower())
        self.assertGreaterEqual(len(safe_rep["blocking_layer_attribution"]), 4)

    def test_allowed_targets_rail_and_kill_switch(self) -> None:
        with self.assertRaises(PermissionError):
            validate_allowed_target("https://external-production.example.com")

        os.environ["REDTEAM_KILL_SWITCH"] = "true"
        try:
            with self.assertRaises(PermissionError):
                validate_allowed_target("in_process_safe")
        finally:
            os.environ.pop("REDTEAM_KILL_SWITCH", None)

    def test_safety_goldens_draft_gate(self) -> None:
        with self.assertRaises(RuntimeError):
            load_safety_goldens(allow_draft=False)
        rep = evaluate_safety_goldens(allow_draft=True)
        self.assertEqual(rep["metrics"]["safety_refusal_and_scope_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
