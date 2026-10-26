"""Outcome Review, Steward Write-Back Gate, Anti-Contamination & Calibration Stats (`agents/outcomes/service.py`)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from alba_one.agents.decision_state import transition_decision_state
from alba_one.agents.outcomes.models import (
    ActualVsPredictedDelta,
    HypothesisOutcomeLabel,
    LessonType,
    ProposedLessonDraft,
    compare_actual_vs_predicted,
    intersect_most_restrictive_acl_tags,
)
from alba_one.guardrails.prompt_layer import scan_for_secrets
from alba_one.kb.extractors import KnowledgeDocumentRecord
from alba_one.kb.indexer import InMemoryOnPremStore, InMemoryPineconeStore, KnowledgeBaseIndexer
from alba_one.kb.pii import PIIRedactor
from alba_one.memory.long_term import InMemoryLongTermAdapter, MemoryService

__all__ = [
    "ActualVsPredictedDelta",
    "OutcomeAndWriteBackService",
    "ProposedLessonDraft",
    "compare_actual_vs_predicted",
    "intersect_most_restrictive_acl_tags",
]


class OutcomeAndWriteBackService:
    """Manages Step 1 Outcome Reviews, Step 2 Steward Write-Backs, and Calibration Statistics."""

    def __init__(
        self,
        *,
        kb_indexer: KnowledgeBaseIndexer | None = None,
        memory_service: MemoryService | None = None,
        writeback_requires_different_person: bool = True,
        min_outcomes_for_stats: int = 10,  # TODO(owner): tune from calibration_eval.py
        min_evidence_for_strong_lesson: int = 3,  # TODO(owner)
    ) -> None:
        self.kb_indexer = kb_indexer or KnowledgeBaseIndexer(
            onprem_store=InMemoryOnPremStore(),
            vector_store=InMemoryPineconeStore(),
        )
        self.memory_service = memory_service or MemoryService(adapter=InMemoryLongTermAdapter())
        self.writeback_requires_different_person = writeback_requires_different_person
        self.min_outcomes_for_stats = min_outcomes_for_stats
        self.min_evidence_for_strong_lesson = min_evidence_for_strong_lesson
        self.outcomes: dict[str, dict[str, Any]] = {}
        self.lessons: dict[str, ProposedLessonDraft] = {}
        self.overdue_reminders_sent: int = 0

    def submit_outcome_review(
        self,
        *,
        decision_record: dict[str, Any],
        reviewer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Step 1: Record an outcome review (`POST /api/v1/decisions/{decision_id}/outcomes`)."""
        if "write_back_approved" in payload:
            raise ValueError(
                "write_back_approved is not accepted in the outcome submission payload. "
                "Write-back requires a separate call to POST /api/v1/outcomes/{outcome_id}/write-back by a knowledge_steward."
            )

        cur_state = decision_record["state"]
        if cur_state not in ("approved", "approved_with_conditions", "outcome_pending"):
            raise PermissionError(
                f"Outcome review is only allowed for decisions in approved states (got '{cur_state}')."
            )

        actual_kpis: dict[str, float] = {
            str(k): float(v) for k, v in (payload.get("actual_kpis") or {}).items()
        }
        stored_calcs: dict[str, dict[str, Any]] = decision_record.get("stored_calculators") or {}
        comparisons = [
            compare_actual_vs_predicted(
                metric_id=m_id, actual_value=val, calc_result_dict=stored_calcs[m_id]
            ).to_dict()
            for m_id, val in actual_kpis.items()
            if m_id in stored_calcs
        ]

        hyp_labels: dict[str, dict[str, str]] = dict(payload.get("hypothesis_outcomes") or {})
        if not hyp_labels:
            raise ValueError("hypothesis_outcomes (confirmed | refuted | inconclusive with rationale) is required.")

        primary_label: HypothesisOutcomeLabel = next(iter(hyp_labels.values())).get("label", "inconclusive")  # type: ignore[assignment]
        lesson_type: LessonType = (
            "hypothesis_confirmed"
            if primary_label == "confirmed"
            else ("hypothesis_refuted" if primary_label == "refuted" else "process_improvement")
        )

        new_st, _ = transition_decision_state(cur_state, "outcome_reviewed")
        decision_record["state"] = new_st

        outcome_id = f"out_{uuid.uuid4().hex[:10]}"
        lesson_id = f"les_{uuid.uuid4().hex[:10]}"
        topic_key = str(payload.get("topic_key") or f"workflow_{decision_record.get('workflow', 'general')}")
        acl_lists = decision_record.get("source_acl_lists") or [["role:analyst", "role:approver", "role:admin"]]
        inherited_acl = intersect_most_restrictive_acl_tags(acl_lists)

        draft_lesson = ProposedLessonDraft(
            lesson_id=lesson_id,
            outcome_id=outcome_id,
            decision_id=str(decision_record["decision_id"]),
            tenant_id=str(decision_record["tenant_id"]),
            topic_key=topic_key,
            lesson_type=lesson_type,
            statement_ja=str(
                payload.get(
                    "proposed_lesson_ja",
                    f"意思決定 {decision_record['decision_id']} の成果レビュー知見：{payload.get('variance_reason', '')}",
                )
            ),
            statement_en=str(
                payload.get(
                    "proposed_lesson_en",
                    f"Outcome lesson from decision {decision_record['decision_id']}: {payload.get('variance_reason', '')}",
                )
            ),
            source_acl_tags=inherited_acl,
            primary_outcome_label=primary_label,
            reviewer_id=reviewer_id,
        )
        self.lessons[lesson_id] = draft_lesson

        outcome_rec = {
            "outcome_id": outcome_id,
            "decision_id": decision_record["decision_id"],
            "tenant_id": decision_record["tenant_id"],
            "reviewer_id": reviewer_id,
            "actual_kpis": actual_kpis,
            "actual_vs_predicted": comparisons,
            "hypothesis_outcomes": hyp_labels,
            "conditions_status": payload.get("conditions_status") or decision_record.get("tracked_conditions", []),
            "variance_reason": str(payload.get("variance_reason", "")),
            "proposed_lesson": draft_lesson.to_dict(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.outcomes[outcome_id] = outcome_rec
        return outcome_rec

    def approve_lesson_writeback(
        self,
        *,
        outcome_id: str,
        tenant_id: str,
        steward_user_id: str,
        steward_role: str,
        edited_statement_ja: str,
        edited_statement_en: str,
        approved: bool = True,
    ) -> dict[str, Any]:
        """Step 2: Steward reviews, edits, and writes back a lesson (`POST /api/v1/outcomes/{outcome_id}/write-back`)."""
        if steward_role.lower().strip() != "knowledge_steward":
            raise PermissionError(f"Write-back requires 'knowledge_steward' role (got '{steward_role}').")
        outcome = self.outcomes.get(outcome_id)
        if outcome is None or outcome["tenant_id"] != tenant_id:
            raise KeyError(f"Outcome '{outcome_id}' not found for tenant '{tenant_id}'.")

        lesson = self.lessons[outcome["proposed_lesson"]["lesson_id"]]
        if self.writeback_requires_different_person and steward_user_id == lesson.reviewer_id:
            raise PermissionError("WRITEBACK_REQUIRES_DIFFERENT_PERSON: reviewer cannot self-approve write-back.")
        if not approved:
            lesson.status = "rejected"
            return {"status": "rejected", "lesson": lesson.to_dict()}
        if lesson.primary_outcome_label == "inconclusive":
            raise PermissionError("Inconclusive outcomes are not written back to the KB by default.")

        for txt in (edited_statement_ja, edited_statement_en):
            if scan_for_secrets(txt):
                raise PermissionError("Write-back blocked: secret token detected in edited lesson text.")
        redactor = PIIRedactor()
        clean_ja = redactor.redact(edited_statement_ja).redacted_text
        clean_en = redactor.redact(edited_statement_en).redacted_text

        prior_active = [
            old
            for old in self.lessons.values()
            if old.tenant_id == tenant_id
            and old.topic_key == lesson.topic_key
            and old.status == "active"
            and old.lesson_id != lesson.lesson_id
        ]
        for old in prior_active:
            old.status = "superseded"
            old.superseded_by = lesson.lesson_id

        corroborated_total = len(prior_active) + 1
        lesson.corroborated_count = corroborated_total
        lesson.evidence_grade = (
            "corroborated" if corroborated_total >= self.min_evidence_for_strong_lesson else "single_outcome"
        )
        lesson.statement_ja = clean_ja
        lesson.statement_en = clean_en
        lesson.status = "active"
        lesson.approved_by_steward_id = steward_user_id

        docs = [
            KnowledgeDocumentRecord(
                doc_id=f"doc_{lesson.lesson_id}_{lang}",
                tenant_id=tenant_id,
                entity_type="decision",
                entity_ids=[lesson.decision_id, lesson.outcome_id, lesson.lesson_id],
                source_table="decision_outcomes_writeback",
                source_view="v_kb_decisions",
                source_pk=f"{lesson.lesson_id}:{lang}",
                lang=lang,
                title=f"[Past Decision Lesson ({lesson.lesson_type})]",
                text=clean_ja if lang == "ja" else clean_en,
                structured_metadata={
                    "origin": "decision_asset",
                    "lesson_type": lesson.lesson_type,
                    "decision_id": lesson.decision_id,
                    "outcome_id": lesson.outcome_id,
                    "evidence_grade": lesson.evidence_grade,
                    "corroborated_count": lesson.corroborated_count,
                    "status": "active",
                },
                acl_tags=list(lesson.source_acl_tags),
                valid_from=lesson.valid_from,
                valid_to=None,
                updated_at=lesson.valid_from,
            )
            for lang in ("ja", "en")
        ]
        idx_report = self.kb_indexer.run(tenant_id=tenant_id, documents=docs, mode="incremental")

        mem_item = self.memory_service.propose_memory(
            tenant_id=tenant_id,
            user_id=steward_user_id,
            memory_type="approved_decision_fact",
            topic_key=lesson.topic_key,
            content=clean_ja,
            lang="ja",
            approval_id=f"wb_{lesson.lesson_id}",
            user_confirmed=True,
        )
        return {
            "status": "written_back",
            "lesson": lesson.to_dict(),
            "superseded_lesson_ids": [o.lesson_id for o in prior_active],
            "kb_chunks_indexed": idx_report.chunks_upserted,
            "memory_id": mem_item.memory_id,
        }

    def compute_decision_quality_stats(self, *, tenant_id: str) -> dict[str, Any]:
        """Compute calibration stats across reviewed outcomes, gated by `min_outcomes_for_stats`."""
        tenant_outcomes = [o for o in self.outcomes.values() if o["tenant_id"] == tenant_id]
        n = len(tenant_outcomes)
        if n < self.min_outcomes_for_stats:
            return {
                "tenant_id": tenant_id,
                "status": "insufficient_data",
                "message": "not enough data",
                "reviewed_outcomes": n,
                "min_outcomes_for_stats": self.min_outcomes_for_stats,
                "stats": None,
            }
        confirmed = sum(
            1 for o in tenant_outcomes if o["proposed_lesson"]["primary_outcome_label"] == "confirmed"
        )
        return {
            "tenant_id": tenant_id,
            "status": "ok",
            "reviewed_outcomes": n,
            "min_outcomes_for_stats": self.min_outcomes_for_stats,
            "stats": {"confirmed_rate": round(confirmed / n, 4), "confirmed_count": confirmed},
        }

    def check_overdue_outcome_reviews(
        self,
        decisions: list[dict[str, Any]],
        *,
        now_iso: str,
    ) -> list[dict[str, Any]]:
        """Emit reminder events for approved decisions whose `outcome_review_due_at < now_iso`."""
        reminders: list[dict[str, Any]] = []
        for d in decisions:
            due = d.get("outcome_review_due_at")
            if d.get("state") in ("approved", "approved_with_conditions", "outcome_pending") and due and str(due) < now_iso:
                self.overdue_reminders_sent += 1
                reminders.append(
                    {"decision_id": d["decision_id"], "tenant_id": d["tenant_id"], "outcome_review_due_at": due}
                )
        return reminders
