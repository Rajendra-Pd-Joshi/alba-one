"""Decision Judge Runner (`agents/judge/judge.py`).

Builds the deterministic `ComparisonTable`, synthesizes a conclusion-first recommendation
verified through the Phase 6 citation/numeric validator, and enforces the Phase 7
Verdict Ceiling Rules (`gates.py`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import uuid
from typing import Any

from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.hypothesis.validator import ValidatedHypothesis
from alba_one.agents.judge.comparison import (
    ComparisonTable,
    build_comparison_table,
    load_decision_criteria,
)
from alba_one.agents.judge.gates import (
    GateEvaluationResult,
    RecommendationVerdictType,
    apply_verdict_ceiling_gates,
)


@dataclass(frozen=True)
class JudgeRecommendationOutput:
    """Complete recommendation output from the Decision Judge (before human HITL action)."""

    recommendation_id: str
    decision_id: str
    tenant_id: str
    workflow: str
    lang: str
    version: int
    recommendation_hash: str
    ledger_snapshot_id: str
    leading_option_id: str | None
    proposed_verdict: RecommendationVerdictType
    verdict: RecommendationVerdictType
    gates_applied: list[str]
    verdict_overridden_by_rule: str | None
    options_compared: list[str]
    rationale: str
    conditions: list[str]
    risks: list[str]
    cited_hypothesis_ids: list[str]
    cited_evidence_ids: list[str]
    comparison_table: ComparisonTable
    gate_evaluation: GateEvaluationResult = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_recommendation_hash(
    *,
    decision_id: str,
    verdict: str,
    leading_option_id: str | None,
    ledger_snapshot_id: str,
    conditions: list[str],
    version: int,
) -> str:
    """Compute a deterministic SHA-256 hash binding an approval to the exact recommendation state."""
    payload = json.dumps(
        {
            "decision_id": decision_id,
            "verdict": verdict,
            "leading_option_id": leading_option_id,
            "ledger_snapshot_id": ledger_snapshot_id,
            "conditions": sorted(conditions),
            "version": version,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def run_decision_judge(
    *,
    decision_id: str,
    tenant_id: str,
    workflow: str,
    hypotheses: list[ValidatedHypothesis],
    ledger: EvidenceLedger,
    lang: str = "ja",
    proposed_verdict: RecommendationVerdictType = "recommend_approve",
    leading_option_id: str | None = None,
    confidence_threshold: float = 0.70,
    weights_reviewed_by_override: str | None = None,
    qualitative_cells: dict[tuple[str, str], dict[str, str]] | None = None,
    version: int = 1,
) -> JudgeRecommendationOutput:
    """Build `ComparisonTable`, evaluate ceiling rules `a`–`g`, and emit a conclusion-first recommendation."""
    reviewed_by, criteria = load_decision_criteria(
        workflow, weights_reviewed_by_override=weights_reviewed_by_override
    )
    table = build_comparison_table(
        hypotheses,
        ledger,
        criteria,
        workflow=workflow,
        weights_reviewed_by=reviewed_by,
        qualitative_cells=qualitative_cells,
    )

    non_baseline = [h for h in hypotheses if not h.is_baseline]
    lead_id = leading_option_id or (non_baseline[0].hypothesis_id if non_baseline else None)

    gate_res = apply_verdict_ceiling_gates(
        proposed_verdict=proposed_verdict,
        leading_option_id=lead_id,
        hypotheses=hypotheses,
        comparison_table=table,
        confidence_threshold=confidence_threshold,
    )

    final_verdict = gate_res.final_verdict
    cited_hyps = [h.hypothesis_id for h in hypotheses]
    cited_evs = sorted({c.evidence_id for h in hypotheses for c in h.citations})
    base_conditions = list(gate_res.auto_added_conditions)
    if final_verdict == "recommend_approve_with_conditions" and not base_conditions:
        base_conditions.append(
            "Monitor canary metrics and verify operational constraints during initial rollout."
            if lang == "en"
            else "初期ロールアウト中のカナリア指標および運用制約の遵守をモニタリングすること。"
        )

    # Conclusion-first rationale in the user's active language
    if lang == "ja":
        rationale = (
            f"【結論：{final_verdict}（対象案：{lead_id or 'なし'}）】"
            f"比較対象 {len(hypotheses)} 案（必須ベースライン案を含む）を決定論的比較表で検証した結果、"
            f"適用ゲート {gate_res.gates_applied or ['なし']} に基づき `{final_verdict}` を推奨します。"
            f"参照エビデンス：{', '.join(cited_evs) or 'なし'}。"
        )
    else:
        rationale = (
            f"[Conclusion: {final_verdict} (Leading Option: {lead_id or 'none'})] "
            f"Across {len(hypotheses)} options (including mandatory baseline), deterministic table and ceiling gates "
            f"{gate_res.gates_applied or ['none']} yield `{final_verdict}`. "
            f"Cited evidence: {', '.join(cited_evs) or 'none'}."
        )

    ledger_snap = f"lsnap_{hashlib.sha256(json.dumps(cited_evs).encode('utf-8')).hexdigest()[:12]}"
    rec_hash = compute_recommendation_hash(
        decision_id=decision_id,
        verdict=final_verdict,
        leading_option_id=lead_id,
        ledger_snapshot_id=ledger_snap,
        conditions=base_conditions,
        version=version,
    )

    return JudgeRecommendationOutput(
        recommendation_id=f"rec_{uuid.uuid4().hex[:10]}",
        decision_id=decision_id,
        tenant_id=tenant_id,
        workflow=workflow,
        lang=lang,
        version=version,
        recommendation_hash=rec_hash,
        ledger_snapshot_id=ledger_snap,
        leading_option_id=lead_id,
        proposed_verdict=proposed_verdict,
        verdict=final_verdict,
        gates_applied=gate_res.gates_applied,
        verdict_overridden_by_rule=gate_res.verdict_overridden_by_rule,
        options_compared=[h.option_label for h in hypotheses] or ["none"],
        rationale=rationale,
        conditions=base_conditions,
        risks=[r for h in hypotheses for r in h.risks][:5],
        cited_hypothesis_ids=cited_hyps,
        cited_evidence_ids=cited_evs,
        comparison_table=table,
        gate_evaluation=gate_res,
    )
