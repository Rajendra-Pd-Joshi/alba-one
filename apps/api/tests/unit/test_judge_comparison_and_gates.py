"""Unit tests for Phase 7 Deterministic Comparison Table & Verdict Ceiling Gates a-g (`test_judge_comparison_and_gates.py`)."""

from __future__ import annotations

from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.hypothesis.validator import ResolvedEvidenceCitation, ValidatedHypothesis
from alba_one.agents.judge.comparison import (
    ComparisonCell,
    ComparisonTable,
    CriterionSpec,
    OptionComparisonRow,
    build_comparison_table,
    load_decision_criteria,
)
from alba_one.agents.judge.gates import apply_verdict_ceiling_gates


def _make_hyp(
    hid: str,
    *,
    is_baseline: bool = False,
    stance: str = "support",
    confidence: float = 0.85,
    external_only: bool = False,
) -> ValidatedHypothesis:
    return ValidatedHypothesis(
        hypothesis_id=hid,
        option_label=f"Option {hid}",
        is_baseline=is_baseline,
        statement=f"Statement for {hid}",
        stance=stance,  # type: ignore[arg-type]
        rationale="Grounded rationale",
        assumptions=["Assumption 1"],
        risks=["Risk 1"],
        what_would_change_my_mind="Falsifier 1",
        citations=[
            ResolvedEvidenceCitation(
                evidence_id="ev_001",
                source_type="external_result" if external_only else "calculator_result",
                source_id="src_1",
                url="https://example.com" if external_only else None,
                retrieved_at="2026-10-24T00:00:00Z",
                external=external_only,
            )
        ],
        confidence_score=confidence,
    )


def _single_criterion_table(
    spec: CriterionSpec,
    cell: ComparisonCell,
) -> ComparisonTable:
    row = OptionComparisonRow(
        hypothesis_id="H1",
        option_label="Option H1",
        is_baseline=False,
        cells={spec.id: cell},
        all_hard_constraints_passed=(cell.hard_constraint_passed is not False),
        has_violated_hard_constraint=(cell.hard_constraint_passed is False),
    )
    return ComparisonTable(
        workflow="test",
        criteria=[spec],
        rows=[row],
        weights_reviewed_by="TODO(owner)",
        weighted_score_status="weights_not_reviewed",
    )


class TestJudgeComparisonAndGates(unittest.TestCase):
    """Test Verdict Ceiling Rules a-g, ComparisonTable, JP/EN criteria parity, and unreviewed weights."""

    def test_gate_a_hard_constraint_unverified_caps_at_needs_more_info(self) -> None:
        spec = CriterionSpec(
            id="article36_overtime_margin",
            name_ja="36協定残業余裕",
            name_en="Article 36 Overtime Margin",
            unit="hours/month",
            direction="higher_better",
            kind="hard_constraint",
            required=True,
            source_id="staffing.calculate_overtime_margin",
            locator="value",
            is_regulatory_or_safety=True,
        )
        cell = ComparisonCell("article36_overtime_margin", "parameters_not_verified", None, "hours/month")
        table = _single_criterion_table(spec, cell)
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id="H1",
            hypotheses=[_make_hyp("H1"), _make_hyp("H_BASE", is_baseline=True)],
            comparison_table=table,
        )
        self.assertEqual(res.final_verdict, "needs_more_info")
        self.assertIn("gate_a_hard_constraint_unverified_or_insufficient:article36_overtime_margin", res.gates_applied)
        self.assertIsNotNone(res.verdict_overridden_by_rule)

    def test_gate_b_soft_criterion_insufficient_caps_at_approve_with_conditions(self) -> None:
        spec = CriterionSpec(
            id="route_cost_jpy",
            name_ja="配送費用",
            name_en="Route Cost",
            unit="JPY",
            direction="lower_better",
            kind="soft_criterion",
            required=True,
            source_id="delivery_planning.calculate_route_cost_jpy",
            locator="value",
        )
        cell = ComparisonCell("route_cost_jpy", "insufficient_data", None, "JPY")
        table = _single_criterion_table(spec, cell)
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id="H1",
            hypotheses=[_make_hyp("H1"), _make_hyp("H_BASE", is_baseline=True)],
            comparison_table=table,
        )
        self.assertEqual(res.final_verdict, "recommend_approve_with_conditions")
        self.assertIn("gate_b_soft_criterion_unverified_or_insufficient:route_cost_jpy", res.gates_applied)
        self.assertTrue(any("Verify route_cost_jpy" in c for c in res.auto_added_conditions))

    def test_gate_c_no_valid_hypotheses_returns_needs_more_info(self) -> None:
        spec = CriterionSpec("c1", "基準1", "Criterion 1", "ms", "lower_better", "soft_criterion", True, "s", "v")
        table = ComparisonTable("test", [spec], [], "TODO(owner)", "weights_not_reviewed")
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id=None,
            hypotheses=[],
            comparison_table=table,
        )
        self.assertEqual(res.final_verdict, "needs_more_info")
        self.assertIn("gate_c_no_valid_hypotheses", res.gates_applied)

    def test_gate_d_hard_constraint_violated_caps_at_recommend_reject(self) -> None:
        spec = CriterionSpec(
            id="sla_breach_probability",
            name_ja="SLA超過確率",
            name_en="SLA Breach Probability",
            unit="probability",
            direction="lower_better",
            kind="hard_constraint",
            required=True,
            source_id="delivery.sla",
            locator="value",
            hard_limit=0.35,
        )
        cell = ComparisonCell("sla_breach_probability", "ok", 0.65, "probability", hard_constraint_passed=False)
        table = _single_criterion_table(spec, cell)
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id="H1",
            hypotheses=[_make_hyp("H1"), _make_hyp("H_BASE", is_baseline=True)],
            comparison_table=table,
        )
        self.assertEqual(res.final_verdict, "recommend_reject")
        self.assertIn("gate_d_hard_constraint_violated:sla_breach_probability", res.gates_applied)

    def test_gate_e_low_confidence_caps_at_approve_with_conditions(self) -> None:
        spec = CriterionSpec("c1", "基準1", "Criterion 1", "ms", "lower_better", "soft_criterion", False, "s", "v")
        table = _single_criterion_table(spec, ComparisonCell("c1", "ok", 10.0, "ms"))
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id="H1",
            hypotheses=[_make_hyp("H1", confidence=0.55), _make_hyp("H_BASE", is_baseline=True)],
            comparison_table=table,
            confidence_threshold=0.70,
        )
        self.assertEqual(res.final_verdict, "recommend_approve_with_conditions")
        self.assertIn("gate_e_confidence_below_threshold", res.gates_applied)

    def test_gate_f_external_evidence_only_caps_at_approve_with_conditions(self) -> None:
        spec = CriterionSpec("c1", "基準1", "Criterion 1", "ms", "lower_better", "soft_criterion", False, "s", "v")
        table = _single_criterion_table(spec, ComparisonCell("c1", "ok", 10.0, "ms"))
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id="H1",
            hypotheses=[_make_hyp("H1", external_only=True), _make_hyp("H_BASE", is_baseline=True)],
            comparison_table=table,
        )
        self.assertEqual(res.final_verdict, "recommend_approve_with_conditions")
        self.assertIn("gate_f_external_evidence_only", res.gates_applied)

    def test_gate_g_contradicted_by_higher_confidence_opposing_hypothesis(self) -> None:
        spec = CriterionSpec("c1", "基準1", "Criterion 1", "ms", "lower_better", "soft_criterion", False, "s", "v")
        table = _single_criterion_table(spec, ComparisonCell("c1", "ok", 10.0, "ms"))
        res = apply_verdict_ceiling_gates(
            proposed_verdict="recommend_approve",
            leading_option_id="H1",
            hypotheses=[
                _make_hyp("H1", stance="support", confidence=0.75),
                _make_hyp("H2", stance="oppose", confidence=0.88),
                _make_hyp("H_BASE", is_baseline=True),
            ],
            comparison_table=table,
        )
        self.assertEqual(res.final_verdict, "recommend_approve_with_conditions")
        self.assertIn("gate_g_contradicted_by_opposing_hypothesis", res.gates_applied)

    def test_missing_data_and_weights_not_reviewed_and_jp_en_parity(self) -> None:
        for wf in ("delivery_planning", "staffing", "vessel_allocation", "model_release", "default"):
            rev_by, specs = load_decision_criteria(wf)
            self.assertTrue(rev_by.startswith("TODO(owner)"))
            self.assertGreaterEqual(len(specs), 3)
            for s in specs:
                self.assertTrue(s.name_ja.strip())
                self.assertTrue(s.name_en.strip())
                self.assertNotEqual(s.name_ja, s.name_en)

        # Build table with empty ledger -> numeric cells stay "missing", qualitative cells "no_evidence", weighted_total None
        empty_ledger = EvidenceLedger("tenant_alba_demo")
        rev_by, specs = load_decision_criteria("delivery_planning")
        table = build_comparison_table(
            [_make_hyp("H1"), _make_hyp("H_BASE", is_baseline=True)],
            empty_ledger,
            specs,
            workflow="delivery_planning",
            weights_reviewed_by=rev_by,
        )
        self.assertEqual(table.weighted_score_status, "weights_not_reviewed")
        for row in table.rows:
            self.assertIsNone(row.weighted_total)
            self.assertEqual(row.cells["sla_breach_probability"].status, "missing")
            self.assertIsNone(row.cells["sla_breach_probability"].value)
            self.assertEqual(row.cells["reversibility"].status, "no_evidence")


if __name__ == "__main__":
    unittest.main()
