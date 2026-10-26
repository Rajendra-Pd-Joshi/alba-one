"""End-to-End Decision OS Orchestrator (`agents/workflow.py`).

Connects the complete ALBA ONE core loop:
  Ask -> Clarify -> Retrieve -> Hypothesise (Phase 6) -> Judge (Phase 7)
  -> Human Approval (`awaiting_approval` -> `approval_recorded_resume_pending` -> `approved*`)
  -> Outcome Review (`outcome_reviewed`) -> Steward Write-Back (`decision_asset`).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import json
from typing import Any
import uuid

from alba_one.agents.decision_state import transition_decision_state
from alba_one.agents.hitl.service import HITLApprovalService
from alba_one.agents.hypothesis.graph import run_hypothesis_pipeline
from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.judge.judge import run_decision_judge
from alba_one.agents.outcomes.service import OutcomeAndWriteBackService


class DecisionOSWorkflowService:
    """End-to-end stateful service coordinating Hypotheses, Judge, HITL Outbox, and Outcomes."""

    def __init__(
        self,
        *,
        hitl_service: HITLApprovalService | None = None,
        outcomes_service: OutcomeAndWriteBackService | None = None,
    ) -> None:
        self.hitl = hitl_service or HITLApprovalService()
        self.outcomes = outcomes_service or OutcomeAndWriteBackService()
        self.decisions: dict[str, dict[str, Any]] = self.hitl.decisions

    def create_decision(
        self,
        *,
        question: str,
        tenant_id: str,
        requester_id: str,
        workflow: str = "delivery_planning",
        lang: str = "ja",
        proposed_verdict: str = "recommend_approve",
    ) -> dict[str, Any]:
        """Execute `POST /api/v1/decisions`: run 2-round hypothesis gathering + Decision Judge and pause at `awaiting_approval`."""
        decision_id = f"dec_{uuid.uuid4().hex[:10]}"
        state = "draft"
        state, _ = transition_decision_state(state, "gathering")

        hyp_run = run_hypothesis_pipeline(question, tenant_id=tenant_id, lang=lang)
        state, _ = transition_decision_state(state, "hypotheses_ready")

        ledger = EvidenceLedger(tenant_id=tenant_id)
        stored_calcs: dict[str, dict[str, Any]] = {}
        for item_dict in hyp_run.ledger_items:
            ledger.register_item(
                tenant_id=item_dict["tenant_id"],
                source_type=item_dict["source_type"],
                source_id=item_dict["source_id"],
                tool_call_id=item_dict.get("tool_call_id"),
                url=item_dict.get("url"),
                retrieved_at=item_dict.get("retrieved_at"),
                external=bool(item_dict.get("external", False)),
                raw_text=item_dict["raw_text"],
                structured_data=item_dict.get("structured_data", {}),
            )
            if item_dict["source_type"] == "calculator_result":
                fid = str(item_dict.get("structured_data", {}).get("formula_id") or item_dict["source_id"])
                stored_calcs[fid] = item_dict.get("structured_data", {})
                stored_calcs[item_dict["source_id"]] = item_dict.get("structured_data", {})

        judge_rec = run_decision_judge(
            decision_id=decision_id,
            tenant_id=tenant_id,
            workflow=workflow,
            hypotheses=hyp_run.hypotheses,
            ledger=ledger,
            lang=lang,
            proposed_verdict=proposed_verdict,  # type: ignore[arg-type]
        )
        state, _ = transition_decision_state(state, "recommended")
        state, _ = transition_decision_state(state, "awaiting_approval")

        now_utc = datetime.now(timezone.utc)
        record: dict[str, Any] = {
            "decision_id": decision_id,
            "tenant_id": tenant_id,
            "requester_id": requester_id,
            "question": question,
            "workflow": workflow,
            "lang": lang,
            "state": state,
            "version": 1,
            "evidence_loops_used": 0,
            "hypotheses": [h.to_dict() for h in hyp_run.hypotheses],
            "recommendation": judge_rec.to_dict(),
            "stored_calculators": stored_calcs,
            "tracked_conditions": [],
            "approval_due_at": (now_utc + timedelta(hours=24)).isoformat(),
            "outcome_review_due_at": (now_utc + timedelta(days=14)).isoformat(),
            "created_at": now_utc.isoformat(),
        }
        self.hitl.register_decision_for_approval(record)
        return record


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: `uv run python -m alba_one.agents.workflow "<question>" --lang en|ja`."""
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 7 End-to-End Decision Judge & HITL CLI")
    parser.add_argument("question", help="Decision question in Japanese or English")
    parser.add_argument("--workflow", default="model_release")
    parser.add_argument("--lang", default="en", choices=["ja", "en"])
    parser.add_argument("--tenant", default="tenant_alba_demo")
    args = parser.parse_args(argv)

    svc = DecisionOSWorkflowService()
    rec = svc.create_decision(
        question=args.question,
        tenant_id=args.tenant,
        requester_id="usr_requester_01",
        workflow=args.workflow,
        lang=args.lang,
    )
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
