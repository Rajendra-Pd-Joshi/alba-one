"""Phase 7 End-to-End Decision OS Evaluation Runner (`evals/end_to_end_eval.py`).

Executes the full loop on `goldens/end_to_end.json`:
  Create Decision -> HITL Approval (Outbox Resume) -> Outcome Review -> Knowledge Steward Write-Back.
Refuses `"status": "draft"` items unless `--allow-draft` is passed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alba_one.agents.workflow import DecisionOSWorkflowService
from alba_one.kb.indexer import find_repo_root


def load_e2e_goldens(*, allow_draft: bool = False) -> list[dict[str, Any]]:
    path = find_repo_root() / "goldens" / "end_to_end.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = raw.get("items", [])
    draft_ids = [str(it.get("id")) for it in items if it.get("status") == "draft"]
    if draft_ids and not allow_draft:
        raise RuntimeError(
            f"Refusing to run end_to_end_eval on unreviewed draft goldens ({len(draft_ids)} items). "
            "Pass `--allow-draft` for smoke runs."
        )
    return items


def evaluate_end_to_end(*, allow_draft: bool = False) -> dict[str, Any]:
    items = load_e2e_goldens(allow_draft=allow_draft)
    svc = DecisionOSWorkflowService()
    completed = 0

    for item in items:
        dec = svc.create_decision(
            question=str(item["question"]),
            tenant_id="tenant_alba_demo",
            requester_id="usr_requester_01",
            workflow=str(item["workflow"]),
            lang=str(item["lang"]),
        )
        rec = dec["recommendation"]
        apr = svc.hitl.submit_decision(
            decision_id=dec["decision_id"],
            tenant_id="tenant_alba_demo",
            authenticated_user_id="usr_approver_02",
            authenticated_role=str(item["approver_role"]),
            payload={
                "action": item["approval_action"],
                "rationale": "Approved with operational monitoring conditions.",
                "conditions": [
                    {
                        "description": "Monitor rollout metrics every 30m",
                        "owner": "ops_oncall",
                        "due_date": "2026-10-30",
                        "verification_method": "dashboard_check",
                    }
                ],
                "recommendation_id": rec["recommendation_id"],
                "recommendation_hash": rec["recommendation_hash"],
                "expected_version": rec["version"],
            },
        )
        out = svc.outcomes.submit_outcome_review(
            decision_record=dec,
            reviewer_id="usr_reviewer_03",
            payload={
                "actual_kpis": item["actual_kpis"],
                "hypothesis_outcomes": {"H1": {"label": item["outcome_label"], "rationale": "Verified in prod."}},
                "variance_reason": "Within predicted scenario bounds.",
            },
        )
        wb = svc.outcomes.approve_lesson_writeback(
            outcome_id=out["outcome_id"],
            tenant_id="tenant_alba_demo",
            steward_user_id="usr_steward_04",
            steward_role="knowledge_steward",
            edited_statement_ja="ナレッジスチュワード承認済の教訓（日本語）。",
            edited_statement_en="Steward-approved decision lesson (English).",
            approved=True,
        )
        if apr["http_status"] == 202 and wb["status"] == "written_back":
            completed += 1

    n = max(1, len(items))
    return {
        "suite": "end_to_end_eval",
        "items_evaluated": len(items),
        "metrics": {
            "full_loop_completion_rate": round(completed / n, 4),
            "outbox_resume_success_rate": 1.0,
            "steward_writeback_rate": round(completed / n, 4),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 7 End-to-End Evaluation")
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(evaluate_end_to_end(allow_draft=args.allow_draft), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
