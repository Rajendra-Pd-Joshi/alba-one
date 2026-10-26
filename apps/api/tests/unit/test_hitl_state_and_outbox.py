"""Unit tests for Phase 7 HITL State Machine, Concurrency, Separation of Duties & Outbox Resume (`test_hitl_state_and_outbox.py`)."""

from __future__ import annotations

from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.agents.decision_state import (
    ALLOWED_DECISION_TRANSITIONS,
    ALL_DECISION_STATES,
    IllegalDecisionStateTransitionError,
    MaxEvidenceLoopsExceededError,
    transition_decision_state,
)
from alba_one.agents.hitl.outbox import InMemoryCheckpointSaver
from alba_one.agents.hitl.service import (
    HITLApprovalService,
    HITLAuthorizationError,
    StaleApprovalConflictError,
)


def _sample_decision_record(decision_id: str = "dec_test_01") -> dict:
    return {
        "decision_id": decision_id,
        "tenant_id": "tenant_alba_demo",
        "requester_id": "usr_requester_01",
        "workflow": "model_release",
        "state": "awaiting_approval",
        "version": 1,
        "evidence_loops_used": 0,
        "approval_due_at": "2026-10-25T00:00:00+00:00",
        "recommendation": {
            "recommendation_id": "rec_001",
            "recommendation_hash": "hash_abc123",
            "version": 1,
            "verdict": "recommend_approve_with_conditions",
            "ledger_snapshot_id": "lsnap_001",
            "gates_applied": ["gate_e_confidence_below_threshold"],
        },
    }


class TestHITLStateAndOutbox(unittest.TestCase):
    """Test decision transition table, role matrix, separation of duties, stale hash 409, idempotency, and outbox crash recovery."""

    def test_all_legal_and_illegal_transitions_in_state_machine(self) -> None:
        for src_state in ALL_DECISION_STATES:
            allowed_targets = ALLOWED_DECISION_TRANSITIONS[src_state]
            for dst_state in ALL_DECISION_STATES:
                if dst_state in allowed_targets:
                    new_st, _ = transition_decision_state(src_state, dst_state, evidence_loops_used=0, max_evidence_loops=2)
                    self.assertEqual(new_st, dst_state)
                else:
                    with self.assertRaises(IllegalDecisionStateTransitionError):
                        transition_decision_state(src_state, dst_state)

    def test_role_matrix_and_separation_of_duties_and_no_body_approver(self) -> None:
        svc = HITLApprovalService()
        svc.register_decision_for_approval(_sample_decision_record())
        valid_payload = {
            "action": "approve_with_conditions",
            "rationale": "Conditions attached.",
            "conditions": [{"description": "Check canary", "owner": "sre", "due_date": "2026-10-30", "verification_method": "metrics"}],
            "recommendation_id": "rec_001",
            "recommendation_hash": "hash_abc123",
            "expected_version": 1,
        }

        # 1. Passing approver_id in body is rejected
        with self.assertRaises(ValueError):
            svc.submit_decision(
                decision_id="dec_test_01",
                tenant_id="tenant_alba_demo",
                authenticated_user_id="usr_gov_02",
                authenticated_role="ai_governance_lead",
                payload={**valid_payload, "approver_id": "forged_user"},
            )

        # 2. Unauthorized role (viewer / operator) is rejected
        with self.assertRaises(HITLAuthorizationError):
            svc.submit_decision(
                decision_id="dec_test_01",
                tenant_id="tenant_alba_demo",
                authenticated_user_id="usr_viewer_02",
                authenticated_role="viewer",
                payload=valid_payload,
            )

        # 3. Separation of duties: requester cannot approve their own decision
        with self.assertRaises(HITLAuthorizationError):
            svc.submit_decision(
                decision_id="dec_test_01",
                tenant_id="tenant_alba_demo",
                authenticated_user_id="usr_requester_01",
                authenticated_role="ai_governance_lead",
                payload=valid_payload,
            )

    def test_stale_hash_409_and_double_submit_and_idempotency_key(self) -> None:
        svc = HITLApprovalService()
        svc.register_decision_for_approval(_sample_decision_record("dec_idem_01"))

        # Stale hash -> 409 StaleApprovalConflictError
        with self.assertRaises(StaleApprovalConflictError) as ctx:
            svc.submit_decision(
                decision_id="dec_idem_01",
                tenant_id="tenant_alba_demo",
                authenticated_user_id="usr_gov_02",
                authenticated_role="ai_governance_lead",
                payload={
                    "action": "reject",
                    "rationale": "Rejecting.",
                    "recommendation_id": "rec_001",
                    "recommendation_hash": "wrong_stale_hash",
                    "expected_version": 1,
                },
            )
        self.assertEqual(ctx.exception.status_code, 409)

        payload = {
            "action": "approve",
            "rationale": "Diverging from conditional recommendation with explicit rationale.",
            "recommendation_id": "rec_001",
            "recommendation_hash": "hash_abc123",
            "expected_version": 1,
        }
        res1 = svc.submit_decision(
            decision_id="dec_idem_01",
            tenant_id="tenant_alba_demo",
            authenticated_user_id="usr_gov_02",
            authenticated_role="ai_governance_lead",
            payload=payload,
            idempotency_key="idem_key_100",
        )
        self.assertEqual(res1["http_status"], 202)
        self.assertTrue(res1["diverged_from_recommendation"])

        # Same Idempotency-Key + same payload -> returns identical cached 202 response without adding a new event
        res2 = svc.submit_decision(
            decision_id="dec_idem_01",
            tenant_id="tenant_alba_demo",
            authenticated_user_id="usr_gov_02",
            authenticated_role="ai_governance_lead",
            payload=payload,
            idempotency_key="idem_key_100",
        )
        self.assertEqual(res1["approval_id"], res2["approval_id"])
        self.assertEqual(len(svc.approval_events), 1)

        # Double-submit without matching Idempotency-Key -> 409 Conflict
        with self.assertRaises(StaleApprovalConflictError):
            svc.submit_decision(
                decision_id="dec_idem_01",
                tenant_id="tenant_alba_demo",
                authenticated_user_id="usr_gov_02",
                authenticated_role="ai_governance_lead",
                payload=payload,
                idempotency_key="idem_key_200",
            )

    def test_simulated_worker_crash_and_idempotent_outbox_resume(self) -> None:
        cp = InMemoryCheckpointSaver(fail_next_n_calls=1)
        svc = HITLApprovalService(checkpointer=cp)
        svc.register_decision_for_approval(_sample_decision_record("dec_crash_01"))

        res = svc.submit_decision(
            decision_id="dec_crash_01",
            tenant_id="tenant_alba_demo",
            authenticated_user_id="usr_gov_02",
            authenticated_role="ai_governance_lead",
            payload={
                "action": "approve_with_conditions",
                "rationale": "Conditional approval.",
                "conditions": [{"description": "Verify logs", "owner": "sre", "due_date": "2026-10-30", "verification_method": "audit"}],
                "recommendation_id": "rec_001",
                "recommendation_hash": "hash_abc123",
                "expected_version": 1,
            },
        )
        # Worker failed on first attempt -> stays in approval_recorded_resume_pending and increments alert counter
        self.assertEqual(res["state"], "approval_recorded_resume_pending")
        self.assertEqual(res["outbox_status"], "failed_retryable")
        self.assertEqual(svc.alert_counters["outbox_resume_failures"], 1)

        # Retry outbox -> succeeds idempotently and transitions to approved_with_conditions
        completed = svc.retry_pending_outbox()
        self.assertEqual(completed, 1)
        self.assertEqual(svc.decisions["dec_crash_01"]["state"], "approved_with_conditions")

    def test_expiry_and_request_more_evidence_loop_cap(self) -> None:
        svc = HITLApprovalService(max_evidence_loops=2)
        dec_exp = _sample_decision_record("dec_exp_01")
        dec_exp["approval_due_at"] = "2026-10-20T00:00:00+00:00"
        svc.register_decision_for_approval(dec_exp)

        expired = svc.expire_overdue_decisions("2026-10-24T12:00:00+00:00")
        self.assertEqual(len(expired), 1)
        self.assertEqual(dec_exp["state"], "expired")
        self.assertEqual(dec_exp["escalated_to_role"], "cto")

        # Test MAX_EVIDENCE_LOOPS cap on request_more_evidence
        dec_loop = _sample_decision_record("dec_loop_01")
        dec_loop["evidence_loops_used"] = 2
        svc.register_decision_for_approval(dec_loop)
        with self.assertRaises(MaxEvidenceLoopsExceededError):
            svc.submit_decision(
                decision_id="dec_loop_01",
                tenant_id="tenant_alba_demo",
                authenticated_user_id="usr_gov_02",
                authenticated_role="ai_governance_lead",
                payload={
                    "action": "request_more_evidence",
                    "rationale": "Need more runs.",
                    "questions": ["Run 10 more shadow iterations"],
                    "recommendation_id": "rec_001",
                    "recommendation_hash": "hash_abc123",
                    "expected_version": 1,
                },
            )


if __name__ == "__main__":
    unittest.main()
