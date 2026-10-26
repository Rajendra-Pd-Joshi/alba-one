"""Unit tests for Phase 9 Observability, `percentile_cont`, Cost Rules, Privacy & Queue Reliability (`test_observability_and_ops.py`)."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

_BOOTSTRAP = Path(__file__).resolve().parent / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

from alba_one.observability.cost import (
    compute_call_cost,
    convert_usd_to_configured_jpy,
    load_price_table,
    recompute_spans_cost,
    resolve_tokens,
)
from alba_one.observability.queries import (
    aggregate_decision_run_metrics,
    compute_latency_percentiles,
    compute_percentile_cont,
    summarize_spans_grouped,
)
from alba_one.observability.telemetry import BoundedSpanTelemetryRecorder


class TestObservabilityAndOps(unittest.TestCase):
    """Test percentile_cont, cost rules (NULL on unpriced, 0 on cache hit), privacy canary scan, and queue overflow."""

    def test_percentile_cont_hand_computed_and_insufficient_samples(self) -> None:
        # Hand-computed values for [10, 20, 30, 40, 50]:
        # p50 -> index 0.5 * 4 = 2.0 -> 30.0
        # p95 -> index 0.95 * 4 = 3.8 -> 40 + 0.8 * (50 - 40) = 48.0
        vals = [50.0, 10.0, 40.0, 20.0, 30.0]
        self.assertEqual(compute_percentile_cont(vals, 0.50), 30.0)
        self.assertEqual(compute_percentile_cont(vals, 0.95), 48.0)
        self.assertEqual(compute_percentile_cont(vals, 0.99), 49.6)

        # Below min_samples -> returns status="insufficient_samples" and None percentiles
        under = compute_latency_percentiles([10.0, 20.0, 30.0], min_samples=5)
        self.assertEqual(under["status"], "insufficient_samples")
        self.assertEqual(under["sample_size"], 3)
        self.assertIsNone(under["p95_ms"])

    def test_cost_calculator_priced_unpriced_cache_hit_and_recompute(self) -> None:
        pt = load_price_table()
        # 1. Priced model: gpt-4o-2024-08-06 ($2.50 / 1M in, $10.00 / 1M out)
        # 2000 in -> 0.005, 500 out -> 0.005 => total 0.01 USD
        cost, cur, ver, est = compute_call_cost(
            model_or_tool="gpt-4o-2024-08-06",
            tokens_in=2000,
            tokens_out=500,
            cache_hit=False,
            tokens_estimated=False,
            price_table=pt,
        )
        self.assertEqual(cost, 0.01)
        self.assertEqual(cur, "USD")
        self.assertEqual(ver, "2026-10-24.v1")
        self.assertFalse(est)

        # 2. Cache hit -> cost_amount = 0.0, cost_estimated = False
        c_hit, _, _, c_est = compute_call_cost(
            model_or_tool="gpt-4o-2024-08-06",
            tokens_in=2000,
            tokens_out=500,
            cache_hit=True,
            price_table=pt,
        )
        self.assertEqual(c_hit, 0.0)
        self.assertFalse(c_est)

        # 3. Unpriced model or tool -> MUST be cost_amount = None (NULL) and cost_estimated = True, NEVER 0.0!
        unp_cost, _, _, unp_est = compute_call_cost(
            model_or_tool="unknown-custom-tool",
            tokens_in=100,
            tokens_out=50,
            cache_hit=False,
            price_table=pt,
        )
        self.assertIsNone(unp_cost)
        self.assertTrue(unp_est)

        # 4. Token estimation when provider counts are absent
        t_in, t_out, t_est = resolve_tokens(
            reported_tokens_in=None,
            reported_tokens_out=None,
            prompt_text="abcd" * 25,
            output_text="efgh" * 10,
        )
        self.assertEqual(t_in, 25)
        self.assertEqual(t_out, 10)
        self.assertTrue(t_est)

        # 5. Configured JPY conversion
        jpy = convert_usd_to_configured_jpy(1.0, price_table=pt)
        self.assertEqual(jpy["cost_jpy"], 151.45)

    def test_privacy_by_default_and_canary_secret_scan_on_stored_spans(self) -> None:
        secret_canary = "CANARY-ABCDEF1234567890"
        # Mode 1: capture_content=False (prod default) -> stores hashes & sizes only, raw text is None
        rec_prod = BoundedSpanTelemetryRecorder(capture_content=False)
        sp1 = rec_prod.record_span(
            trace_id="tr_1",
            tenant_id="tenant_fictional_alpha",
            run_id="run_1",
            phase_step="hypothesis",
            kind="llm",
            model_or_tool="gpt-4o-2024-08-06",
            provider="openai",
            latency_ms=320.0,
            prompt_text=f"Prompt with {secret_canary} and 090-1234-5678",
            output_text=f"Output with {secret_canary}",
        )
        assert sp1 is not None
        self.assertIsNone(sp1.captured_prompt_redacted)
        self.assertIsNone(sp1.captured_output_redacted)
        self.assertGreater(sp1.prompt_bytes, 10)
        self.assertNotIn(secret_canary, json.dumps(sp1.to_dict()))

        # Mode 2: capture_content=True -> scrubs PII and CANARY before storing!
        rec_dev = BoundedSpanTelemetryRecorder(capture_content=True)
        sp2 = rec_dev.record_span(
            trace_id="tr_2",
            tenant_id="tenant_fictional_alpha",
            run_id="run_2",
            phase_step="hypothesis",
            kind="llm",
            model_or_tool="gpt-4o-2024-08-06",
            provider="openai",
            latency_ms=310.0,
            prompt_text=f"Prompt with {secret_canary} and 090-1234-5678",
            output_text=f"Output with {secret_canary}",
        )
        assert sp2 is not None
        serialized = json.dumps(sp2.to_dict(), ensure_ascii=False)
        self.assertNotIn(secret_canary, serialized)
        self.assertNotIn("090-1234-5678", serialized)

    def test_queue_overflow_db_down_and_langsmith_down_never_break_requests(self) -> None:
        def failing_db(_batch):
            raise RuntimeError("Simulated Postgres outage")

        def failing_langsmith(_span, _meta):
            raise RuntimeError("Simulated LangSmith outage")

        rec = BoundedSpanTelemetryRecorder(
            max_queue_size=2,
            db_writer=failing_db,
            langsmith_exporter=failing_langsmith,
        )
        for i in range(4):
            rec.record_span(
                trace_id="tr_overflow",
                tenant_id="tenant_alba_demo",
                decision_id="dec_1",
                run_id="run_1",
                phase_step="judge",
                kind="llm",
                model_or_tool="gpt-4o-2024-08-06",
                provider="openai",
                latency_ms=100.0 + i,
                reported_tokens_in=100,
                reported_tokens_out=50,
            )
        self.assertEqual(len(rec.queue), 2)
        self.assertEqual(rec.spans_dropped, 2)
        self.assertEqual(rec.langsmith_export_failures, 4)

        flushed = rec.flush()
        self.assertEqual(flushed, 0)
        self.assertEqual(rec.db_write_failures, 1)

    def test_aggregation_of_retries_cache_hits_and_recompute_costs(self) -> None:
        rec = BoundedSpanTelemetryRecorder()
        rec.record_span(
            trace_id="tr_agg", tenant_id="tenant_alba_demo", decision_id="dec_agg", run_id="run_agg",
            phase_step="retrieve", kind="mcp_tool", model_or_tool="knowledge_base.kb_search",
            provider="internal", latency_ms=50.0, cache_hit=True,
        )
        rec.record_span(
            trace_id="tr_agg", tenant_id="tenant_alba_demo", decision_id="dec_agg", run_id="run_agg",
            phase_step="hypothesis", kind="llm", model_or_tool="gpt-4o-2024-08-06",
            provider="openai", latency_ms=400.0, reported_tokens_in=2000, reported_tokens_out=500, retry_count=2,
        )
        rec.record_span(
            trace_id="tr_agg", tenant_id="tenant_alba_demo", decision_id="dec_agg", run_id="run_agg",
            phase_step="tool_call", kind="mcp_tool", model_or_tool="unpriced.tool",
            provider="internal", latency_ms=80.0,
        )
        rec.flush()

        metrics = aggregate_decision_run_metrics(
            rec.flushed_spans, run_id="run_agg", decision_id="dec_agg", tenant_id="tenant_alba_demo"
        )
        self.assertEqual(metrics.retry_count, 2)
        self.assertEqual(metrics.unpriced_calls, 1)
        self.assertEqual(metrics.tool_call_count, 2)
        self.assertAlmostEqual(metrics.cache_hit_ratio, round(1 / 3, 4))

        recomp = recompute_spans_cost(rec.flushed_spans)
        self.assertEqual(recomp["spans_recomputed"], 3)
        self.assertEqual(recomp["unpriced_calls"], 1)

        grouped = summarize_spans_grouped(rec.flushed_spans, tenant_id="tenant_alba_demo", group_by="stage")
        self.assertEqual(grouped["unpriced_calls"], 1)


if __name__ == "__main__":
    unittest.main()
