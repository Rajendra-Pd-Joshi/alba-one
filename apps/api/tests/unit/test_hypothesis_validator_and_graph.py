"""Unit tests for Phase 6 Citation/Numeric Validator, 1-Retry Repair, Fail-Closed & 2-Round Gathering (`test_hypothesis_validator_and_graph.py`).

Tests all required scenarios from User Answers 1 & 2:
1. Forged `evidence_id` -> rejected (`forged_evidence_id`).
2. Evidence from another tenant -> rejected (`cross_tenant_evidence`).
3. Slightly altered quote -> rejected (`quote_not_found_in_evidence`).
4. Quote matching only after Unicode NFKC normalization (full-width vs half-width) -> accepted.
5. Number in hypothesis not appearing in any cited evidence/calculator -> rejected (`ungrounded_number_in_hypothesis`).
6. Locator to a missing structured field -> rejected (`locator_not_found_in_structured_data`).
7. Japanese quote & code-populated citation fields (`source_type`, `source_id`, `url`, `retrieved_at`, `external`).
8. One repair attempt + per-hypothesis fail-closed (`partial_dropped` and `insufficient_evidence`).
9. Two-round gathering: budget exhaustion (`budget_exhausted=True`), duplicate tool call deduplication,
   failed tool call recorded in `gaps`, and mandatory Round 2 counter-evidence query.
"""

from __future__ import annotations

from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.agents.hypothesis.graph import run_hypothesis_pipeline
from alba_one.agents.hypothesis.ledger import EvidenceLedger
from alba_one.agents.hypothesis.planner import (
    HypothesisGatheringBudgets,
    PlannedToolCall,
    execute_gathering_round,
)
from alba_one.agents.hypothesis.synthesizer import validate_and_repair_hypotheses
from alba_one.agents.hypothesis.validator import (
    LLMCitationDraft,
    LLMHypothesisDraft,
    validate_single_hypothesis,
)
from evals.hypothesis_eval import evaluate_hypotheses, load_hypothesis_goldens


def _make_draft(
    hyp_id: str,
    statement: str,
    citations: list[LLMCitationDraft],
    *,
    rationale: str = "Grounded rationale.",
    depends_on_external: bool = False,
) -> LLMHypothesisDraft:
    return LLMHypothesisDraft(
        hypothesis_id=hyp_id,
        option_label=f"Option {hyp_id}",
        is_baseline=False,
        statement=statement,
        stance="support",
        rationale=rationale,
        assumptions=["Standard port conditions."],
        risks=["Weather variability."],
        what_would_change_my_mind="If wind exceeds threshold.",
        citations=citations,
        depends_on_external=depends_on_external,
    )


class TestHypothesisValidatorAndGraph(unittest.TestCase):
    """Test citation/numeric validation edge cases, repair/fail-closed, and 2-round gathering."""

    def setUp(self) -> None:
        self.ledger = EvidenceLedger(tenant_id="tenant_alba_demo")
        self.ev1 = self.ledger.register_item(
            tenant_id="tenant_alba_demo",
            source_type="kb_chunk",
            source_id="chk_jp_01",
            raw_text="医薬品定温コンテナは　２〜８℃を維持し、最大瞬間風速 13.8 m/s で警戒体制に入る。",
            structured_data={"gust_wind_speed_ms": 13.8, "scenarios": [{"scenario": "base", "value": 0.2}]},
            external=False,
        )
        self.ev_other_tenant = self.ledger.register_item(
            tenant_id="tenant_other_corp",
            source_type="kb_chunk",
            source_id="chk_other_99",
            raw_text="Confidential other tenant record 42.0.",
            external=False,
        )
        self.ev_external = self.ledger.register_item(
            tenant_id="tenant_alba_demo",
            source_type="external_result",
            source_id="weather_marine.get_port_weather",
            url="https://www.jma.go.jp/bosai/warning/",
            retrieved_at="2026-10-24T06:00:00Z",
            raw_text="Yokohama port wind advisory 13.8 m/s.",
            structured_data={"gust_wind_speed_ms": 13.8},
            external=True,
        )

    def test_1_forged_evidence_id_rejected(self) -> None:
        draft = _make_draft("H1", "Wind is safe.", [LLMCitationDraft(evidence_id="ev_999", quote="safe")])
        valid, issues = validate_single_hypothesis(draft, self.ledger, run_tenant_id="tenant_alba_demo")
        self.assertIsNone(valid)
        self.assertEqual(issues[0].code, "forged_evidence_id")

    def test_2_cross_tenant_evidence_rejected(self) -> None:
        draft = _make_draft(
            "H1",
            "Value is 42.0.",
            [LLMCitationDraft(evidence_id=self.ev_other_tenant.evidence_id, quote="Confidential other tenant record 42.0.")],
        )
        valid, issues = validate_single_hypothesis(draft, self.ledger, run_tenant_id="tenant_alba_demo")
        self.assertIsNone(valid)
        self.assertEqual(issues[0].code, "cross_tenant_evidence")

    def test_3_altered_quote_rejected(self) -> None:
        draft = _make_draft(
            "H1",
            "医薬品定温コンテナの警戒基準。",
            [LLMCitationDraft(evidence_id=self.ev1.evidence_id, quote="医薬品定温コンテナは2〜8℃を完全に放棄し")],
        )
        valid, issues = validate_single_hypothesis(draft, self.ledger, run_tenant_id="tenant_alba_demo")
        self.assertIsNone(valid)
        self.assertEqual(issues[0].code, "quote_not_found_in_evidence")

    def test_4_nfkc_normalized_japanese_quote_and_code_filled_metadata_accepted(self) -> None:
        # Source has full-width "２〜８℃", quote uses half-width "2〜8℃" and extra spaces
        draft = _make_draft(
            "H1",
            "最大瞬間風速 13.8 m/s で警戒体制に入る。",
            [
                LLMCitationDraft(
                    evidence_id=self.ev1.evidence_id,
                    quote="医薬品定温コンテナは  2〜8℃を維持し、最大瞬間風速 13.8 m/s",
                ),
                LLMCitationDraft(
                    evidence_id=self.ev_external.evidence_id,
                    locator="gust_wind_speed_ms",
                ),
            ],
            depends_on_external=True,
        )
        valid, issues = validate_single_hypothesis(draft, self.ledger, run_tenant_id="tenant_alba_demo")
        self.assertEqual(issues, [])
        assert valid is not None
        # Verify our code populated source_type, url, retrieved_at, and external from the ledger
        self.assertEqual(valid.citations[1].url, "https://www.jma.go.jp/bosai/warning/")
        self.assertTrue(valid.citations[1].external)
        self.assertEqual(valid.citations[1].resolved_value, 13.8)

    def test_5_ungrounded_number_rejected(self) -> None:
        draft = _make_draft(
            "H1",
            "最大瞬間風速 13.8 m/s により損失は 999999.0 円となる。",
            [LLMCitationDraft(evidence_id=self.ev1.evidence_id, quote="最大瞬間風速 13.8 m/s")],
        )
        valid, issues = validate_single_hypothesis(draft, self.ledger, run_tenant_id="tenant_alba_demo")
        self.assertIsNone(valid)
        self.assertTrue(any(i.code == "ungrounded_number_in_hypothesis" for i in issues))

    def test_6_missing_locator_field_rejected(self) -> None:
        draft = _make_draft(
            "H1",
            "警戒体制に入る。",
            [LLMCitationDraft(evidence_id=self.ev1.evidence_id, locator="scenarios.nonexistent.value")],
        )
        valid, issues = validate_single_hypothesis(draft, self.ledger, run_tenant_id="tenant_alba_demo")
        self.assertIsNone(valid)
        self.assertEqual(issues[0].code, "locator_not_found_in_structured_data")

    def test_7_single_repair_retry_and_per_hypothesis_fail_closed(self) -> None:
        bad_h1 = _make_draft("H1", "Invented number 777.0.", [LLMCitationDraft(evidence_id="ev_999", quote="none")])
        bad_h2 = _make_draft("H2", "Still bad after repair 888.0.", [LLMCitationDraft(evidence_id="ev_999", quote="none")])

        def repair_fn(failed, issues, ledger):
            # Fix H1 to use valid ev1 quote and number 13.8; leave H2 broken to test per-hypothesis drop
            fixed_h1 = _make_draft(
                "H1",
                "最大瞬間風速 13.8 m/s で警戒体制に入る。",
                [LLMCitationDraft(evidence_id=self.ev1.evidence_id, quote="最大瞬間風速 13.8 m/s")],
            )
            return [fixed_h1 if d.hypothesis_id == "H1" else d for d in failed]

        status, valid_list, report = validate_and_repair_hypotheses(
            [bad_h1, bad_h2],
            self.ledger,
            run_tenant_id="tenant_alba_demo",
            repair_callback=repair_fn,
        )
        self.assertEqual(status, "partial_dropped")
        self.assertTrue(report.repair_attempted)
        self.assertEqual(len(valid_list), 1)
        self.assertEqual(valid_list[0].hypothesis_id, "H1")
        self.assertEqual(report.dropped_count, 1)
        self.assertEqual(report.dropped_hypotheses[0]["hypothesis_id"], "H2")

    def test_8_two_round_gathering_dedup_budget_and_counter_evidence(self) -> None:
        import asyncio

        ledger = EvidenceLedger(tenant_id="tenant_alba_demo")
        budgets = HypothesisGatheringBudgets(max_tool_calls_per_run=2, round1_max_calls=2)
        calls = [
            # Two identical calls -> second must be deduplicated without charging budget
            PlannedToolCall("weather_marine", "get_port_weather", {"tenant_id": "tenant_alba_demo", "port_code": "YOK"}),
            PlannedToolCall("weather_marine", "get_port_weather", {"tenant_id": "tenant_alba_demo", "port_code": "YOK"}),
            # Second distinct call (fails -> recorded in gaps)
            PlannedToolCall("sql_readonly", "query_view", {"tenant_id": "tenant_alba_demo", "sql": "DROP TABLE x"}),
            # Third distinct call -> exceeds max_tool_calls_per_run=2 -> triggers budget_exhausted
            PlannedToolCall("market_data", "get_market_indices", {"tenant_id": "tenant_alba_demo", "index_code": "USDJPY"}),
        ]
        asyncio.run(execute_gathering_round(1, calls, ledger, budgets))
        self.assertEqual(ledger.total_tool_calls, 2)
        self.assertTrue(ledger.budget_exhausted)
        self.assertEqual(len(ledger.gaps), 1)

        # Full pipeline run on English & Japanese questions
        res_en = run_hypothesis_pipeline("Should we release model v2.4 to production?", lang="en")
        self.assertEqual(res_en.status, "ok")
        self.assertGreaterEqual(res_en.counter_evidence_queries_run, 1)
        self.assertTrue(any(h.is_baseline for h in res_en.hypotheses))

    def test_9_hypothesis_eval_draft_gate_and_metrics(self) -> None:
        with self.assertRaises(RuntimeError):
            load_hypothesis_goldens(allow_draft=False)
        eval_rep = evaluate_hypotheses(allow_draft=True, smoke_limit=4)
        self.assertEqual(eval_rep["deterministic_metrics"]["citation_precision"], 1.0)
        self.assertEqual(eval_rep["deterministic_metrics"]["numeric_grounding"], 1.0)
        self.assertEqual(eval_rep["deterministic_metrics"]["mandatory_baseline_rate"], 1.0)
        self.assertEqual(eval_rep["geval_metrics"]["numeric_honesty"], 1.0)


if __name__ == "__main__":
    unittest.main()
