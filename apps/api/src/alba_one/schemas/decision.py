"""Decision, Hypothesis, Recommendation, Approval, Outcome, and Guardrail schemas (Pydantic v2).

Implements the ALBA ONE core loop:
Ask -> Clarify -> Retrieve -> Hypothesise -> Judge -> Human approval -> Outcome review.
Per Phase 7 User Answer 0:
- AI Judge produces `RecommendationVerdict`:
  `recommend_approve | recommend_approve_with_conditions | recommend_reject | needs_more_info`
- Human Approver produces `ApprovalAction`:
  `approve | approve_with_conditions | reject | request_more_evidence`
Never mix the two enums.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alba_one.schemas.common import Evidence, Language


class HypothesisStance(StrEnum):
    """Position a hypothesis takes toward a proposed option."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    NEUTRAL = "neutral"


class RecommendationVerdict(StrEnum):
    """AI Judge recommendation verdict (subject to human approval per Principle 4)."""

    RECOMMEND_APPROVE = "recommend_approve"
    RECOMMEND_APPROVE_WITH_CONDITIONS = "recommend_approve_with_conditions"
    RECOMMEND_REJECT = "recommend_reject"
    NEEDS_MORE_INFO = "needs_more_info"


class ApprovalAction(StrEnum):
    """Human decision maker's action on a recommendation."""

    APPROVE = "approve"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REJECT = "reject"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"


class GuardrailLayer(StrEnum):
    """Defense-in-depth guardrail layers (Principle 5)."""

    PROMPT = "prompt"
    INPUT = "input"
    OUTPUT = "output"
    RETRIEVER = "retriever"
    TOOL = "tool"
    HITL = "hitl"
    OPS = "ops"


class GuardrailAction(StrEnum):
    """Enforcement action taken by a guardrail."""

    PASS = "pass"
    BLOCK = "block"
    MASK = "mask"
    ESCALATE = "escalate"


class DecisionRequest(BaseModel):
    """User request initiating a Decision OS workflow."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1, max_length=8000)
    language: Language = Field(default=Language.JA)
    workflow_domain: str = Field(
        default="delivery_planning",
        description="e.g. delivery_planning, vessel_allocation, staffing, model_release",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class ConfidenceBreakdown(BaseModel):
    """Transparent decomposition of hypothesis confidence (確信度)."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(..., ge=0.0, le=1.0, description="Composite confidence score in [0, 1]")
    evidence_strength: float = Field(..., ge=0.0, le=1.0)
    coverage: float = Field(..., ge=0.0, le=1.0)
    consistency: float = Field(..., ge=0.0, le=1.0)
    judge_notes: str = Field(..., min_length=1)
    lang: Language = Field(default=Language.JA)


class Hypothesis(BaseModel):
    """An evidence-backed hypothesis (仮説) evaluated during option analysis."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    stance: HypothesisStance
    rationale: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(..., min_length=1, description="At least one citation required")
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: ConfidenceBreakdown
    lang: Language = Field(default=Language.JA)

    @model_validator(mode="after")
    def verify_evidence_present(self) -> Hypothesis:
        """Reject uncited hypotheses at schema boundary (Principle 3: Evidence-first)."""
        if not self.evidence:
            raise ValueError("Hypothesis must include at least one Evidence citation.")
        return self


class DecisionRecommendation(BaseModel):
    """Judge output comparing options and recommending a conditional action."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    verdict: RecommendationVerdict
    options_compared: list[str] = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    conditions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    cited_hypothesis_ids: list[str] = Field(default_factory=list)
    gates_applied: list[str] = Field(default_factory=list)
    verdict_overridden_by_rule: str | None = Field(default=None)
    lang: Language = Field(default=Language.JA)

    @model_validator(mode="after")
    def require_citations_when_decisive(self) -> DecisionRecommendation:
        """Decisive recommendations must cite at least one hypothesis ID."""
        if self.verdict in (
            RecommendationVerdict.RECOMMEND_APPROVE,
            RecommendationVerdict.RECOMMEND_APPROVE_WITH_CONDITIONS,
            RecommendationVerdict.RECOMMEND_REJECT,
        ):
            if not self.cited_hypothesis_ids:
                raise ValueError("Decisive recommendations must cite hypothesis IDs.")
        return self


class TrackedConditionSchema(BaseModel):
    """Structured condition attached to `approve_with_conditions`."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., min_length=1)
    owner: str = Field(..., min_length=1)
    due_date: str = Field(..., min_length=1)
    verification_method: str = Field(..., min_length=1)
    status: str = Field(default="open")
    waived_reason: str | None = Field(default=None)


class ApprovalRecord(BaseModel):
    """Append-only human approval, conditional approval, rejection, or evidence request."""

    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    approver_id: str = Field(..., min_length=1, description="Resolved from authenticated context")
    approver_role: str = Field(..., min_length=1, description="Resolved from authenticated context")
    action: ApprovalAction
    rationale: str | None = Field(default=None)
    conditions: list[TrackedConditionSchema] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    diverged_from_recommendation: bool = Field(default=False)
    recommendation_id: str = Field(..., min_length=1)
    recommendation_hash: str = Field(..., min_length=1)
    expected_version: int = Field(..., ge=1)
    ledger_snapshot_id: str = Field(..., min_length=1)
    gates_applied: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    lang: Language = Field(default=Language.JA)


class OutcomeRecord(BaseModel):
    """Post-decision outcome review (成果レビュー)."""

    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    measured_result: str = Field(..., min_length=1)
    variance_reason: str = Field(..., min_length=1)
    reviewed_by: str = Field(..., min_length=1)
    writeback_chunk_id: str | None = Field(default=None)
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    lang: Language = Field(default=Language.JA)


class GuardrailEvent(BaseModel):
    """Audit event emitted by any of the 7 guardrail layers (ガードレール)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    decision_id: str | None = Field(default=None)
    layer: GuardrailLayer
    action: GuardrailAction
    policy: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lang: Language = Field(default=Language.JA)
