"""Unit tests for Phase 7 Outcome Review, Steward Write-Back Gate, Anti-Contamination & Stats (`test_outcomes_and_writeback.py`)."""

from __future__ import annotations

from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.hypothesis.validator import compute_hypothesis_confidence
from alba_one.agents.outcomes.service import OutcomeAndWriteBackService


def _approved_decision(decision_id: str = "dec_out_01") -> dict:
    return {
        "decision_id": decision_id,
        "tenant_id": "tenant_alba_demo",
        "workflow": "delivery_planning",
        "state": "approved_with_conditions",
        "source_acl_lists": [
            ["role:viewer", "role:analyst", "role:approver", "role:admin"],
            ["role:approver", "role:admin"],
        ],
        "stored_calculators": {
            "delivery.route_cost_jpy": {
                "value": 141000.0,
                "unit": "JPY",
                "scenarios": [
                    {"scenario": "low", "value": 133160.0},
                    {"scenario": "base", "value": 141000.0},
                    {"scenario": "high", "value": 155700.0},
                ],
            }
        },
        "tracked_conditions": [{"condition_id": "cond_01", "status": "done"}],
        "outcome_review_due_at": "2026-10-20T00:00:00+00:00",
    }


class TestOutcomesAndWriteBack(unittest.TestCase):
    """Test outcome review math, separate steward gate, same-person rule, ACL inheritance, PII scrub, supersede, Pinecone text-free, and stats threshold."""

    def test_writeback_flag_rejected_in_outcome_submission_and_deterministic_comparison(self) -> None:
        svc = OutcomeAndWriteBackService(min_outcomes_for_stats=3)
        dec = _approved_decision()

        with self.assertRaises(ValueError):
            svc.submit_outcome_review(
                decision_record=dec,
                reviewer_id="usr_rev_01",
                payload={"write_back_approved": True, "hypothesis_outcomes": {"H1": {"label": "confirmed"}}},
            )

        out = svc.submit_outcome_review(
            decision_record=dec,
            reviewer_id="usr_rev_01",
            payload={
                "topic_key": "tyo_ngo_cold_chain",
                "actual_kpis": {"delivery.route_cost_jpy": 148050.0},
                "hypothesis_outcomes": {"H1": {"label": "confirmed", "rationale": "Met SLA"}},
                "variance_reason": "Fuel slightly above base.",
            },
        )
        self.assertEqual(dec["state"], "outcome_reviewed")
        comp = out["actual_vs_predicted"][0]
        self.assertEqual(comp["delta_from_base"], 7050.0)
        self.assertEqual(comp["pct_delta_from_base"], 5.0)
        self.assertTrue(comp["within_low_high_range"])
        # Most restrictive ACL intersection of the two lists is ["role:admin", "role:approver"]
        self.assertEqual(out["proposed_lesson"]["source_acl_tags"], ["role:admin", "role:approver"])

    def test_steward_role_and_same_person_rule_and_pii_scrub_and_pinecone_no_text(self) -> None:
        svc = OutcomeAndWriteBackService(min_outcomes_for_stats=3)
        dec = _approved_decision("dec_wb_01")
        out = svc.submit_outcome_review(
            decision_record=dec,
            reviewer_id="usr_rev_01",
            payload={
                "topic_key": "tyo_ngo_cold_chain",
                "actual_kpis": {"delivery.route_cost_jpy": 141000.0},
                "hypothesis_outcomes": {"H1": {"label": "confirmed", "rationale": "Exact match"}},
                "variance_reason": "On target.",
            },
        )

        # 1. Blocked without knowledge_steward role
        with self.assertRaises(PermissionError):
            svc.approve_lesson_writeback(
                outcome_id=out["outcome_id"],
                tenant_id="tenant_alba_demo",
                steward_user_id="usr_other_02",
                steward_role="approver",
                edited_statement_ja="教訓テスト",
                edited_statement_en="Lesson test",
            )

        # 2. Blocked when steward_user_id == reviewer_id (same-person rule)
        with self.assertRaises(PermissionError):
            svc.approve_lesson_writeback(
                outcome_id=out["outcome_id"],
                tenant_id="tenant_alba_demo",
                steward_user_id="usr_rev_01",
                steward_role="knowledge_steward",
                edited_statement_ja="教訓テスト",
                edited_statement_en="Lesson test",
            )

        # 3. Valid steward write-back with PII in edited text -> scrubbed, indexed, and proposed to memory
        wb1 = svc.approve_lesson_writeback(
            outcome_id=out["outcome_id"],
            tenant_id="tenant_alba_demo",
            steward_user_id="usr_steward_99",
            steward_role="knowledge_steward",
            edited_statement_ja="担当者 090-1234-5678 への連絡は不要。東京〜名古屋定温便はB3着岸でSLA遵守。",
            edited_statement_en="Contact 090-1234-5678 redacted. Tokyo-Nagoya cold-chain met SLA via B3.",
        )
        self.assertEqual(wb1["status"], "written_back")
        self.assertNotIn("090-1234-5678", wb1["lesson"]["statement_ja"])
        self.assertGreaterEqual(wb1["kb_chunks_indexed"], 2)

        # Verify Pinecone vector store contains ZERO raw text in metadata
        for ns_vecs in svc.kb_indexer.vectors.namespaces.values():
            for _vid, (_vec, meta) in ns_vecs.items():
                self.assertNotIn("text", meta)
                self.assertNotIn("raw_text", meta)

        # Verify MemoryService received the approved memory proposal
        memories = svc.memory_service.list_my_memories(tenant_id="tenant_alba_demo", user_id="usr_steward_99")
        self.assertEqual(len(memories), 1)
        self.assertNotIn("090-1234-5678", memories[0].content)

        # 4. Second outcome on the same topic_key supersedes the first lesson without deleting it
        dec2 = _approved_decision("dec_wb_02")
        out2 = svc.submit_outcome_review(
            decision_record=dec2,
            reviewer_id="usr_rev_01",
            payload={
                "topic_key": "tyo_ngo_cold_chain",
                "actual_kpis": {"delivery.route_cost_jpy": 140000.0},
                "hypothesis_outcomes": {"H1": {"label": "confirmed", "rationale": "Confirmed again"}},
                "variance_reason": "Second confirmation.",
            },
        )
        wb2 = svc.approve_lesson_writeback(
            outcome_id=out2["outcome_id"],
            tenant_id="tenant_alba_demo",
            steward_user_id="usr_steward_99",
            steward_role="knowledge_steward",
            edited_statement_ja="第2回確認済教訓：東京〜名古屋定温便は安定稼働。",
            edited_statement_en="Second corroborated lesson: Tokyo-Nagoya route stable.",
        )
        first_lesson_id = wb1["lesson"]["lesson_id"]
        self.assertIn(first_lesson_id, wb2["superseded_lesson_ids"])
        self.assertEqual(svc.lessons[first_lesson_id].status, "superseded")
        self.assertEqual(svc.lessons[first_lesson_id].superseded_by, wb2["lesson"]["lesson_id"])

    def test_anti_contamination_ledger_label_and_stats_sample_threshold(self) -> None:
        # 1. Retrieved lesson with origin="decision_asset" is labelled past_decision_lesson in ledger
        ledger = EvidenceLedger("tenant_alba_demo")
        lesson_item = ledger.add_kb_chunk(
            chunk_id="chk_lesson_01",
            text="過去の意思決定教訓：B3バース優先着岸が有効。",
            metadata={"origin": "decision_asset", "evidence_grade": "single_outcome", "corroborated_count": 1},
        )
        self.assertEqual(lesson_item.source_type, "past_decision_lesson")
        self.assertIn("PAST DECISION LESSON", ledger.format_for_prompt())
        # Single-outcome lesson alone must NOT raise hypothesis confidence above baseline (0.45)
        self.assertEqual(compute_hypothesis_confidence([lesson_item]), 0.45)

        # 2. Stats hidden below MIN_OUTCOMES_FOR_STATS
        svc = OutcomeAndWriteBackService(min_outcomes_for_stats=5)
        stats_res = svc.compute_decision_quality_stats(tenant_id="tenant_alba_demo")
        self.assertEqual(stats_res["status"], "insufficient_data")
        self.assertEqual(stats_res["message"], "not enough data")
        self.assertIsNone(stats_res["stats"])

        # 3. Overdue outcome review reminders
        reminders = svc.check_overdue_outcome_reviews([_approved_decision("dec_overdue_01")], now_iso="2026-10-24T12:00:00+00:00")
        self.assertEqual(len(reminders), 1)
        self.assertEqual(svc.overdue_reminders_sent, 1)


if __name__ == "__main__":
    unittest.main()
