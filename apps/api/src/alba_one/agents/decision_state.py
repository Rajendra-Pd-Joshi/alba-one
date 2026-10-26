"""Explicit Decision Lifecycle State Machine (`agents/decision_state.py`).

Per Phase 7 User Answer 2:
- Plain dictionary of allowed transitions (`ALLOWED_DECISION_TRANSITIONS`).
- Any illegal transition raises `IllegalDecisionStateTransitionError`.
- `request_more_evidence` moves to `needs_evidence` and re-enters `gathering` with the
  approver's questions; re-entries are capped by `MAX_EVIDENCE_LOOPS` (default 2).
"""

from __future__ import annotations

from typing import Literal

DecisionStateType = Literal[
    "draft",
    "clarifying",
    "gathering",
    "hypotheses_ready",
    "recommended",
    "awaiting_approval",
    "approval_recorded_resume_pending",
    "approved",
    "approved_with_conditions",
    "rejected",
    "needs_evidence",
    "expired",
    "cancelled",
    "outcome_pending",
    "outcome_reviewed",
    "closed",
]

ALL_DECISION_STATES: tuple[DecisionStateType, ...] = (
    "draft",
    "clarifying",
    "gathering",
    "hypotheses_ready",
    "recommended",
    "awaiting_approval",
    "approval_recorded_resume_pending",
    "approved",
    "approved_with_conditions",
    "rejected",
    "needs_evidence",
    "expired",
    "cancelled",
    "outcome_pending",
    "outcome_reviewed",
    "closed",
)

# Explicit state transition table
ALLOWED_DECISION_TRANSITIONS: dict[DecisionStateType, frozenset[DecisionStateType]] = {
    "draft": frozenset({"clarifying", "gathering", "cancelled"}),
    "clarifying": frozenset({"gathering", "cancelled"}),
    "gathering": frozenset({"hypotheses_ready", "recommended", "cancelled"}),
    "hypotheses_ready": frozenset({"recommended", "gathering", "cancelled"}),
    "recommended": frozenset({"awaiting_approval", "cancelled"}),
    "awaiting_approval": frozenset(
        {
            "approval_recorded_resume_pending",
            "approved",
            "approved_with_conditions",
            "rejected",
            "needs_evidence",
            "expired",
            "cancelled",
        }
    ),
    "approval_recorded_resume_pending": frozenset(
        {
            "approved",
            "approved_with_conditions",
            "rejected",
            "needs_evidence",
        }
    ),
    "needs_evidence": frozenset({"gathering", "cancelled"}),
    "approved": frozenset({"outcome_pending", "outcome_reviewed", "closed"}),
    "approved_with_conditions": frozenset({"outcome_pending", "outcome_reviewed", "closed"}),
    "outcome_pending": frozenset({"outcome_reviewed", "closed"}),
    "outcome_reviewed": frozenset({"closed"}),
    "rejected": frozenset({"closed"}),
    "expired": frozenset({"awaiting_approval", "cancelled", "closed"}),
    "cancelled": frozenset({"closed"}),
    "closed": frozenset(),
}


class IllegalDecisionStateTransitionError(ValueError):
    """Raised when a decision lifecycle transition is not in `ALLOWED_DECISION_TRANSITIONS`."""

    def __init__(self, current_state: str, target_state: str) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            f"Illegal decision state transition: '{current_state}' -> '{target_state}'."
        )


class MaxEvidenceLoopsExceededError(RuntimeError):
    """Raised when `request_more_evidence` re-entries exceed `MAX_EVIDENCE_LOOPS`."""

    def __init__(self, loops_used: int, max_loops: int) -> None:
        self.loops_used = loops_used
        self.max_loops = max_loops
        super().__init__(
            f"Exceeded MAX_EVIDENCE_LOOPS ({loops_used}/{max_loops}) for request_more_evidence."
        )


def transition_decision_state(
    current_state: DecisionStateType,
    target_state: DecisionStateType,
    *,
    evidence_loops_used: int = 0,
    max_evidence_loops: int = 2,
) -> tuple[DecisionStateType, int]:
    """Validate `(current_state -> target_state)` and return `(new_state, updated_evidence_loops_used)`."""
    allowed = ALLOWED_DECISION_TRANSITIONS.get(current_state, frozenset())
    if target_state not in allowed:
        raise IllegalDecisionStateTransitionError(current_state, target_state)

    new_loops = evidence_loops_used
    if target_state == "needs_evidence":
        if evidence_loops_used >= max_evidence_loops:
            raise MaxEvidenceLoopsExceededError(evidence_loops_used, max_evidence_loops)
        new_loops = evidence_loops_used + 1

    return target_state, new_loops
