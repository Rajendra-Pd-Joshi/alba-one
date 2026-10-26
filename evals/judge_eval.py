"""Phase 7 Decision Judge Evaluation Runner (`evals/judge_eval.py`).

Evaluates `agents/judge/judge.py` and `agents/judge/gates.py` against `goldens/judge.json`.
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


def load_judge_goldens(*, allow_draft: bool = False) -> list[dict[str, Any]]:
    path = find_repo_root() / "goldens" / "judge.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = raw.get("items", [])
    draft_ids = [str(it.get("id")) for it in items if it.get("status") == "draft"]
    if draft_ids and not allow_draft:
        raise RuntimeError(
            f"Refusing to run judge_eval on unreviewed draft goldens ({len(draft_ids)} items). "
            "Pass `--allow-draft` for smoke runs."
        )
    return items


def evaluate_judge(*, allow_draft: bool = False, smoke_limit: int | None = None) -> dict[str, Any]:
    items = load_judge_goldens(allow_draft=allow_draft)
    if smoke_limit is not None and smoke_limit > 0:
        items = items[:smoke_limit]

    svc = DecisionOSWorkflowService()
    ceiling_matches = 0
    citation_ok = 0
    weights_hidden_ok = 0

    for item in items:
        dec = svc.create_decision(
            question=str(item["question"]),
            tenant_id="tenant_alba_demo",
            requester_id="usr_eval_req",
            workflow=str(item["workflow"]),
            lang=str(item["lang"]),
            proposed_verdict=str(item.get("proposed_verdict", "recommend_approve")),
        )
        rec = dec["recommendation"]
        if rec["gate_evaluation"]["ceiling_verdict"] == item["expected_ceiling"]:
            ceiling_matches += 1
        if rec["cited_hypothesis_ids"] and rec["cited_evidence_ids"]:
            citation_ok += 1
        if rec["comparison_table"]["weighted_score_status"] == "weights_not_reviewed":
            weights_hidden_ok += 1

    n = max(1, len(items))
    return {
        "suite": "judge_eval",
        "items_evaluated": len(items),
        "metrics": {
            "ceiling_gate_accuracy": round(ceiling_matches / n, 4),
            "recommendation_citation_coverage": round(citation_ok / n, 4),
            "unreviewed_weights_suppressed_rate": round(weights_hidden_ok / n, 4),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 7 Decision Judge Evaluation")
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--smoke", type=int, default=None)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate_judge(allow_draft=args.allow_draft, smoke_limit=args.smoke), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
