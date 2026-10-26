"""HITL Approval Service (`agents/hitl/service.py`)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from alba_one.agents.decision_state import (
    DecisionStateType,
    MaxEvidenceLoopsExceededError,
    transition_decision_state,
)
from alba_one.agents.hitl.outbox import (
    CheckpointResumePort,
    InMemoryCheckpointSaver,
    OutboxResumeRow,
    process_outbox_row,
)

ApprovalActionType = Literal[
    "approve",
    "approve_with_conditions",
    "reject",
    "request_more_evidence",
]

HITL_WORKFLOW_POLICY: dict[str, dict[str, Any]] = {
    "delivery_planning": {
        "allowed_roles": frozenset({"approver", "admin", "logistics_director", "port_director"}),
        "escalation_role": "vp_supply_chain",
        "allow_self_approval": False,
        "required_approvals": 1,  # TODO(owner)
    },
    "staffing": {
        "allowed_roles": frozenset({"approver", "admin", "hr_director", "port_director"}),
        "escalation_role": "chief_compliance_officer",
        "allow_self_approval": False,
        "required_approvals": 1,
    },
    "vessel_allocation": {
        "allowed_roles": frozenset({"approver", "admin", "port_director", "port_captain"}),
        "escalation_role": "maritime_safety_vp",
        "allow_self_approval": False,
        "required_approvals": 1,
    },
    "model_release": {
        "allowed_roles": frozenset({"approver", "admin", "ai_governance_lead"}),
        "escalation_role": "cto",
        "allow_self_approval": False,
        "required_approvals": 1,
    },
}


class StaleApprovalConflictError(RuntimeError):
    """Raised (HTTP 409) when `recommendation_hash`, `expected_version`, or state is stale."""

    status_code = 409

    def __init__(self, message_ja: str, message_en: str) -> None:
        self.message_ja = message_ja
        self.message_en = message_en
        super().__init__(f"[409 CONFLICT] {message_ja} / {message_en}")


class HITLAuthorizationError(PermissionError):
    """Raised (HTTP 403) on unauthorized role or separation-of-duties violation."""


@dataclass
class TrackedCondition:
    """Tracked approval condition (`status`: `open | done | waived`)."""

    condition_id: str
    description: str
    owner: str
    due_date: str
    verification_method: str
    status: Literal["open", "done", "waived"] = "open"
    waived_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AppendOnlyApprovalEvent:
    """Immutable append-only approval record written in the same transaction as the outbox row."""

    approval_id: str
    decision_id: str
    tenant_id: str
    approver_id: str
    approver_role: str
    action: ApprovalActionType
    rationale: str
    conditions: list[TrackedCondition]
    questions: list[str]
    diverged_from_recommendation: bool
    recommendation_id: str
    recommendation_hash: str
    expected_version: int
    ledger_snapshot_id: str
    gates_applied: list[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HITLApprovalService:
    """Manages append-only HITL approvals, concurrency binding, outbox writes, and expiry."""

    def __init__(
        self,
        *,
        checkpointer: CheckpointResumePort | None = None,
        max_evidence_loops: int = 2,
    ) -> None:
        self.checkpointer = checkpointer or InMemoryCheckpointSaver()
        self.max_evidence_loops = max_evidence_loops
        self.decisions: dict[str, dict[str, Any]] = {}
        self.approval_events: list[AppendOnlyApprovalEvent] = []
        self.outbox: list[OutboxResumeRow] = []
        self.idempotency_store: dict[str, dict[str, Any]] = {}
        self.alert_counters: dict[str, int] = {"outbox_resume_failures": 0}

    def register_decision_for_approval(self, decision_record: dict[str, Any]) -> None:
        self.decisions[str(decision_record["decision_id"])] = decision_record

    def submit_decision(
        self,
        *,
        decision_id: str,
        tenant_id: str,
        authenticated_user_id: str,
        authenticated_role: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        auto_run_worker: bool = True,
    ) -> dict[str, Any]:
        """Validate and record an `ApprovalAction`, writing the approval + outbox row atomically."""
        if "approver_id" in payload or "approver_role" in payload:
            raise ValueError("approver_id and approver_role must come from authenticated context, not request body.")

        if idempotency_key:
            idem_scope = f"{tenant_id}:{decision_id}:{idempotency_key}"
            if idem_scope in self.idempotency_store:
                cached = self.idempotency_store[idem_scope]
                if cached["payload"] == payload:
                    return cached["response"]
                raise StaleApprovalConflictError(
                    "同一のIdempotency-Keyで異なるペイロードが送信されました。",
                    "Idempotency-Key reused with a different request payload.",
                )

        dec = self.decisions.get(decision_id)
        if dec is None or dec.get("tenant_id") != tenant_id:
            raise KeyError(f"Decision '{decision_id}' not found for tenant '{tenant_id}'.")

        workflow = str(dec.get("workflow", "delivery_planning"))
        policy = HITL_WORKFLOW_POLICY.get(workflow, HITL_WORKFLOW_POLICY["delivery_planning"])
        if authenticated_role.lower().strip() not in policy["allowed_roles"]:
            raise HITLAuthorizationError(f"Role '{authenticated_role}' is not authorized for '{workflow}'.")
        if authenticated_user_id == dec.get("requester_id") and not policy.get("allow_self_approval", False):
            raise HITLAuthorizationError("Separation of duties violation: requester cannot approve their own decision.")

        rec = dec["recommendation"]
        if (
            payload.get("recommendation_id") != rec["recommendation_id"]
            or payload.get("recommendation_hash") != rec["recommendation_hash"]
            or int(payload.get("expected_version", -1)) != int(rec["version"])
        ):
            raise StaleApprovalConflictError(
                "表示以降に推奨内容またはエビデンスが更新されています。",
                "Recommendation hash or version changed since display; refresh before deciding.",
            )
        if dec["state"] != "awaiting_approval":
            raise StaleApprovalConflictError(
                f"意思決定 '{decision_id}' は既に '{dec['state']}' に遷移しています。",
                f"Decision '{decision_id}' is no longer in 'awaiting_approval' (current: '{dec['state']}').",
            )

        action: ApprovalActionType = payload["action"]
        rationale = str(payload.get("rationale") or "").strip()
        diverged = (action == "approve" and str(rec["verdict"]) != "recommend_approve")
        if action in ("reject", "request_more_evidence", "approve_with_conditions") or diverged:
            if not rationale:
                raise ValueError(f"rationale is mandatory for action='{action}' (diverged={diverged}).")

        raw_conds = payload.get("conditions") or []
        if action == "approve_with_conditions" and not raw_conds:
            raise ValueError("conditions list is mandatory for action='approve_with_conditions'.")
        tracked_conds = [
            TrackedCondition(
                condition_id=f"cond_{i + 1:02d}",
                description=str(c["description"]),
                owner=str(c["owner"]),
                due_date=str(c["due_date"]),
                verification_method=str(c["verification_method"]),
            )
            for i, c in enumerate(raw_conds)
        ]

        questions = [str(q) for q in (payload.get("questions") or []) if str(q).strip()]
        if action == "request_more_evidence":
            if not questions:
                raise ValueError("questions list is mandatory for action='request_more_evidence'.")
            loops_used = int(dec.get("evidence_loops_used", 0))
            if loops_used >= self.max_evidence_loops:
                raise MaxEvidenceLoopsExceededError(loops_used, self.max_evidence_loops)

        target_map: dict[ApprovalActionType, DecisionStateType] = {
            "approve": "approved",
            "approve_with_conditions": "approved_with_conditions",
            "reject": "rejected",
            "request_more_evidence": "needs_evidence",
        }
        pending_state, _ = transition_decision_state(dec["state"], "approval_recorded_resume_pending")
        dec["state"] = pending_state
        dec["version"] = int(dec.get("version", 1)) + 1
        rec["version"] = dec["version"]
        if tracked_conds:
            dec["tracked_conditions"] = [c.to_dict() for c in tracked_conds]

        event = AppendOnlyApprovalEvent(
            approval_id=f"apr_{uuid.uuid4().hex[:10]}",
            decision_id=decision_id,
            tenant_id=tenant_id,
            approver_id=authenticated_user_id,
            approver_role=authenticated_role,
            action=action,
            rationale=rationale,
            conditions=tracked_conds,
            questions=questions,
            diverged_from_recommendation=diverged,
            recommendation_id=str(rec["recommendation_id"]),
            recommendation_hash=str(rec["recommendation_hash"]),
            expected_version=int(payload["expected_version"]),
            ledger_snapshot_id=str(rec["ledger_snapshot_id"]),
            gates_applied=list(rec.get("gates_applied", [])),
        )
        self.approval_events.append(event)

        outbox_row = OutboxResumeRow(
            outbox_id=f"outbox_{uuid.uuid4().hex[:10]}",
            decision_id=decision_id,
            tenant_id=tenant_id,
            approval_id=event.approval_id,
            target_state=target_map[action],
            resume_payload={"approval_id": event.approval_id, "action": action, "questions": questions},
        )
        self.outbox.append(outbox_row)

        if auto_run_worker:
            process_outbox_row(
                outbox_row, dec, self.checkpointer, alert_counter=self.alert_counters, max_evidence_loops=self.max_evidence_loops
            )

        response = {
            "http_status": 202,
            "decision_id": decision_id,
            "approval_id": event.approval_id,
            "state": dec["state"],
            "outbox_status": outbox_row.status,
            "diverged_from_recommendation": diverged,
            "tracked_conditions": dec.get("tracked_conditions", []),
        }
        if idempotency_key:
            self.idempotency_store[f"{tenant_id}:{decision_id}:{idempotency_key}"] = {
                "payload": payload,
                "response": response,
            }
        return response

    def retry_pending_outbox(self) -> int:
        completed = 0
        for row in self.outbox:
            if row.status != "completed":
                dec = self.decisions[row.decision_id]
                if process_outbox_row(
                    row, dec, self.checkpointer, alert_counter=self.alert_counters, max_evidence_loops=self.max_evidence_loops
                ):
                    completed += 1
        return completed

    def expire_overdue_decisions(self, now_iso: str) -> list[dict[str, Any]]:
        expired_list: list[dict[str, Any]] = []
        for dec in self.decisions.values():
            due = dec.get("approval_due_at")
            if dec["state"] == "awaiting_approval" and due and str(due) < now_iso:
                new_st, _ = transition_decision_state(dec["state"], "expired")
                dec["state"] = new_st
                wf = str(dec.get("workflow", "delivery_planning"))
                esc = HITL_WORKFLOW_POLICY.get(wf, HITL_WORKFLOW_POLICY["delivery_planning"])["escalation_role"]
                dec["escalated_to_role"] = esc
                expired_list.append({"decision_id": dec["decision_id"], "escalated_to_role": esc})
        return expired_list
