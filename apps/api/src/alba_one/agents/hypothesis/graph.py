"""LangGraph Subgraph & CLI for Phase 6 Hypothesis Generation (`agents/hypothesis/graph.py`).

Executes the bounded 2-round shared gathering flow:
  Round 1 (broad gathering + calculators)
  -> Draft hypotheses & gap check
  -> Round 2 (targeted gap-filling + >= 1 counter-evidence query)
  -> Final synthesis (candidate options + mandatory baseline hypothesis)
  -> Deterministic citation & numeric-grounding validation (1 repair attempt -> fail closed per hypothesis)

CLI:
  uv run python -m alba_one.agents.hypothesis.graph "Should we release model v2.4 to production?" --lang en
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from typing import Any

from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.hypothesis.planner import (
    HypothesisGatheringBudgets,
    build_round1_plan,
    build_round2_plan,
    execute_gathering_round,
)
from alba_one.agents.hypothesis.synthesizer import (
    LLMHypothesisDraft,
    ValidationReport,
    build_default_hypothesis_drafts,
    validate_and_repair_hypotheses,
)
from alba_one.agents.hypothesis.validator import HypothesisValidationIssue, ValidatedHypothesis


@dataclass(frozen=True)
class HypothesisRunResult:
    """Complete output of the Phase 6 Hypothesis Generator subgraph (no ranking/verdict)."""

    tenant_id: str
    question: str
    lang: str
    status: str  # "ok" | "partial_dropped" | "insufficient_evidence"
    hypotheses: list[ValidatedHypothesis]
    validation_report: ValidationReport
    budget_exhausted: bool
    budget_exhausted_reason: str | None
    total_tool_calls: int
    round1_calls: int
    round2_calls: int
    counter_evidence_queries_run: int
    gaps: list[dict[str, Any]]
    ledger_items: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "question": self.question,
            "lang": self.lang,
            "status": self.status,
            "has_mandatory_baseline": any(h.is_baseline for h in self.hypotheses),
            "hypothesis_count": len(self.hypotheses),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "validation_report": self.validation_report.to_dict(),
            "budget_exhausted": self.budget_exhausted,
            "budget_exhausted_reason": self.budget_exhausted_reason,
            "total_tool_calls": self.total_tool_calls,
            "round1_calls": self.round1_calls,
            "round2_calls": self.round2_calls,
            "counter_evidence_queries_run": self.counter_evidence_queries_run,
            "gaps": self.gaps,
            "ledger_items": self.ledger_items,
        }


async def run_hypothesis_pipeline_async(
    question: str,
    *,
    tenant_id: str = "tenant_alba_demo",
    lang: str = "ja",
    budgets: HypothesisGatheringBudgets | None = None,
    tool_executor: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
    draft_generator: Callable[[str, EvidenceLedger, str, int], list[LLMHypothesisDraft]] | None = None,
    repair_callback: Callable[
        [list[LLMHypothesisDraft], list[HypothesisValidationIssue], EvidenceLedger],
        list[LLMHypothesisDraft],
    ]
    | None = None,
) -> HypothesisRunResult:
    """Run the 2-round gathering, synthesis, and deterministic validation workflow."""
    active_budgets = budgets or HypothesisGatheringBudgets()
    ledger = EvidenceLedger(tenant_id=tenant_id)

    # Round 1: Plan-driven broad gathering (parallel asyncio.gather with dedup & timeouts)
    r1_plan = build_round1_plan(question, tenant_id=tenant_id, lang=lang)
    await execute_gathering_round(1, r1_plan, ledger, active_budgets, tool_executor=tool_executor)

    # Round 2: Gap check + targeted gap-filling (including >=1 counter-evidence query)
    r2_plan = build_round2_plan(question, ledger, tenant_id=tenant_id, lang=lang)
    counter_queries = sum(1 for c in r2_plan if c.is_counter_evidence_query)
    if not ledger.budget_exhausted:
        await execute_gathering_round(2, r2_plan, ledger, active_budgets, tool_executor=tool_executor)

    # Final synthesis: candidate options + mandatory baseline hypothesis
    if draft_generator is not None:
        drafts = draft_generator(question, ledger, lang, active_budgets.max_options)
    else:
        drafts = build_default_hypothesis_drafts(
            question, ledger, lang=lang, max_options=active_budgets.max_options
        )

    # Deterministic citation & numeric-grounding validation with at most 1 repair retry
    status, valid_hyps, val_report = validate_and_repair_hypotheses(
        drafts,
        ledger,
        run_tenant_id=tenant_id,
        repair_callback=repair_callback,
    )

    return HypothesisRunResult(
        tenant_id=tenant_id,
        question=question,
        lang=lang,
        status=status,
        hypotheses=valid_hyps,
        validation_report=val_report,
        budget_exhausted=ledger.budget_exhausted,
        budget_exhausted_reason=ledger.budget_exhausted_reason,
        total_tool_calls=ledger.total_tool_calls,
        round1_calls=ledger.round1_calls,
        round2_calls=ledger.round2_calls,
        counter_evidence_queries_run=counter_queries,
        gaps=[g.to_dict() for g in ledger.gaps],
        ledger_items=[it.to_dict() for it in ledger.items()],
    )


def run_hypothesis_pipeline(
    question: str,
    *,
    tenant_id: str = "tenant_alba_demo",
    lang: str = "ja",
    budgets: HypothesisGatheringBudgets | None = None,
    tool_executor: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
    draft_generator: Callable[[str, EvidenceLedger, str, int], list[LLMHypothesisDraft]] | None = None,
    repair_callback: Callable[
        [list[LLMHypothesisDraft], list[HypothesisValidationIssue], EvidenceLedger],
        list[LLMHypothesisDraft],
    ]
    | None = None,
) -> HypothesisRunResult:
    """Synchronous entrypoint for the Phase 6 Hypothesis Generator subgraph."""
    return asyncio.run(
        run_hypothesis_pipeline_async(
            question,
            tenant_id=tenant_id,
            lang=lang,
            budgets=budgets,
            tool_executor=tool_executor,
            draft_generator=draft_generator,
            repair_callback=repair_callback,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: `uv run python -m alba_one.agents.hypothesis.graph "<question>" --lang ja|en`."""
    parser = argparse.ArgumentParser(description="ALBA ONE Phase 6 Hypothesis Generator CLI")
    parser.add_argument("question", help="Decision question in Japanese or English")
    parser.add_argument("--lang", default="ja", choices=["ja", "en"])
    parser.add_argument("--tenant", default="tenant_alba_demo")
    parser.add_argument("--max-options", type=int, default=4)
    args = parser.parse_args(argv)

    budgets = HypothesisGatheringBudgets(max_options=args.max_options)
    res = run_hypothesis_pipeline(
        args.question,
        tenant_id=args.tenant,
        lang=args.lang,
        budgets=budgets,
    )
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
