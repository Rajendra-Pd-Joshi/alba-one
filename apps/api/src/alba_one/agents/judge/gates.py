"""Pure-Python Verdict Ceiling Rules (`agents/judge/gates.py`).

Per Phase 7 User Answer 1:
Applied AFTER the LLM proposes a verdict; the final verdict is equal to or more
conservative than the ceiling, NEVER more permissive.
Rules:
  a. Required criterion for leading option has status `parameters_not_verified`,
     `insufficient_data`, or `missing` on a `hard_constraint` or regulatory/safety param
     -> ceiling `needs_more_info`.
  b. Same status on a required `soft_criterion` -> ceiling `recommend_approve_with_conditions`
     and auto-adds condition `"verify <criterion> before execution"`.
  c. No valid hypotheses after validation -> `needs_more_info`.
  d. A hard constraint is violated by the leading option -> that option cannot be
     recommended (`recommend_reject`, or `needs_more_info` if alternatives are untested).
  e. Confidence of the key supporting hypothesis below configurable threshold (`TODO(owner)`)
     -> ceiling `recommend_approve_with_conditions`.
  f. Key claim supported ONLY by external evidence -> ceiling `recommend_approve_with_conditions`
     with condition to confirm internally.
  g. Contradicted evidence (an opposing hypothesis has higher confidence than the supporting one)
     -> no `recommend_approve` (ceiling `recommend_approve_with_conditions`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from alba_one.agents.hypothesis.validator import ValidatedHypothesis
from alba_one.agents.judge.comparison import ComparisonTable

RecommendationVerdictType = Literal[
    "recommend_approve",
    "recommend_approve_with_conditions",
    "recommend_reject",
    "needs_more_info",
]

# Permissiveness rank: higher rank = more permissive
VERDICT_RANK: dict[RecommendationVerdictType, int] = {
    "needs_more_info": 0,
    "recommend_reject": 1,
    "recommend_approve_with_conditions": 2,
    "recommend_approve": 3,
}


@dataclass(frozen=True)
class GateEvaluationResult:
    """Result of applying Verdict Ceiling Rules `a` through `g`."""

    proposed_verdict: RecommendationVerdictType
    ceiling_verdict: RecommendationVerdictType
    final_verdict: RecommendationVerdictType
    gates_applied: list[str] = field(default_factory=list)
    verdict_overridden_by_rule: str | None = None
    auto_added_conditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_verdict_ceiling_gates(
    *,
    proposed_verdict: RecommendationVerdictType,
    leading_option_id: str | None,
    hypotheses: list[ValidatedHypothesis],
    comparison_table: ComparisonTable,
    confidence_threshold: float = 0.70,  # TODO(owner): calibrate from calibration_eval.py
    alternatives_tested: bool = True,
) -> GateEvaluationResult:
    """Evaluate ceiling rules `a`–`g` and clamp `proposed_verdict` to `ceiling_verdict`."""
    gates_applied: list[str] = []
    governing_rule: str | None = None
    ceiling: RecommendationVerdictType = "recommend_approve"
    auto_conditions: list[str] = []

    def _lower_ceiling(target: RecommendationVerdictType, rule_id: str) -> None:
        nonlocal ceiling, governing_rule
        gates_applied.append(rule_id)
        if VERDICT_RANK[target] < VERDICT_RANK[ceiling]:
            ceiling = target
            governing_rule = rule_id
        elif governing_rule is None and VERDICT_RANK[proposed_verdict] > VERDICT_RANK[target]:
            governing_rule = rule_id

    # Rule c: No valid hypotheses after validation -> needs_more_info
    non_baseline = [h for h in hypotheses if not h.is_baseline]
    if not hypotheses or not non_baseline:
        _lower_ceiling("needs_more_info", "gate_c_no_valid_hypotheses")
        final_v: RecommendationVerdictType = "needs_more_info"
        override = "gate_c_no_valid_hypotheses" if proposed_verdict != final_v else None
        return GateEvaluationResult(
            proposed_verdict=proposed_verdict,
            ceiling_verdict=ceiling,
            final_verdict=final_v,
            gates_applied=gates_applied,
            verdict_overridden_by_rule=override,
            auto_added_conditions=auto_conditions,
        )

    lead_hyp = next((h for h in hypotheses if h.hypothesis_id == leading_option_id), non_baseline[0])
    lead_row = next(
        (r for r in comparison_table.rows if r.hypothesis_id == lead_hyp.hypothesis_id),
        comparison_table.rows[0] if comparison_table.rows else None,
    )
    criteria_by_id = {c.id: c for c in comparison_table.criteria}

    if lead_row is not None:
        for cid, cell in lead_row.cells.items():
            c_spec = criteria_by_id.get(cid)
            if c_spec is None:
                continue
            # Rule d: A hard constraint is violated by the leading option
            if cell.hard_constraint_passed is False:
                target_d: RecommendationVerdictType = (
                    "recommend_reject" if alternatives_tested else "needs_more_info"
                )
                _lower_ceiling(target_d, f"gate_d_hard_constraint_violated:{cid}")

            # Rules a & b: Required criterion with parameters_not_verified, insufficient_data, or missing
            if c_spec.required and cell.status in ("parameters_not_verified", "insufficient_data", "missing"):
                if c_spec.kind == "hard_constraint" or c_spec.is_regulatory_or_safety:
                    _lower_ceiling(
                        "needs_more_info",
                        f"gate_a_hard_constraint_unverified_or_insufficient:{cid}",
                    )
                else:
                    _lower_ceiling(
                        "recommend_approve_with_conditions",
                        f"gate_b_soft_criterion_unverified_or_insufficient:{cid}",
                    )
                    auto_conditions.append(f"Verify {cid} ({c_spec.name_en}) before execution.")

    # Rule e: Confidence of the key supporting hypothesis below threshold
    if lead_hyp.confidence_score < confidence_threshold:
        _lower_ceiling(
            "recommend_approve_with_conditions",
            "gate_e_confidence_below_threshold",
        )
        auto_conditions.append(
            f"Validate hypothesis {lead_hyp.hypothesis_id} (confidence {lead_hyp.confidence_score:.2f} < {confidence_threshold:.2f})."
        )

    # Rule f: Key claim supported ONLY by external evidence
    if lead_hyp.citations and all(c.external for c in lead_hyp.citations):
        _lower_ceiling(
            "recommend_approve_with_conditions",
            "gate_f_external_evidence_only",
        )
        auto_conditions.append("Confirm external evidence against internal on-prem records before execution.")

    # Rule g: Contradicted evidence (opposing hypothesis with higher confidence than supporting one)
    opposing = [h for h in hypotheses if h.stance == "oppose"]
    if any(opp.confidence_score > lead_hyp.confidence_score for opp in opposing):
        _lower_ceiling(
            "recommend_approve_with_conditions",
            "gate_g_contradicted_by_opposing_hypothesis",
        )
        auto_conditions.append("Resolve high-confidence opposing hypothesis before full rollout.")

    if VERDICT_RANK[proposed_verdict] > VERDICT_RANK[ceiling]:
        final_verdict = ceiling
        overridden_by = governing_rule or (gates_applied[0] if gates_applied else None)
    else:
        final_verdict = proposed_verdict
        overridden_by = None

    return GateEvaluationResult(
        proposed_verdict=proposed_verdict,
        ceiling_verdict=ceiling,
        final_verdict=final_verdict,
        gates_applied=gates_applied,
        verdict_overridden_by_rule=overridden_by,
        auto_added_conditions=auto_conditions,
    )
