"""Unit tests for Reranker (`cohere_direct` + `gateway` + `FakeReranker`) and `ExternalSearchPort` (`test_reranker_and_external_port.py`)."""

from __future__ import annotations

import importlib.util as _ilu
import json
import pathlib as _pl
import unittest
from typing import Any

import httpx

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from alba_one.retrieval.corrective import run_corrective_rag  # noqa: E402
from alba_one.retrieval.grader import GradedChunkSet  # noqa: E402
from alba_one.retrieval.guardrail_stub import RetrieverGuardrailStub  # noqa: E402
from alba_one.retrieval.ports import ExternalResult, ExternalSearchPort  # noqa: E402
from alba_one.retrieval.reranker import (  # noqa: E402
    FakeReranker,
    HttpReranker,
    RerankerConfigError,
)


class FakeExternalSearch(ExternalSearchPort):
    """Test double implementing `ExternalSearchPort` with configurable results."""

    def __init__(self, results: list[ExternalResult] | None = None) -> None:
        self.results = list(results or [])
        self.calls: list[tuple[str, str, int]] = []

    def search(self, query: str, lang: str, max_results: int = 3) -> list[ExternalResult]:
        self.calls.append((query, lang, max_results))
        return self.results[:max_results]


class TestRerankerAndExternalPort(unittest.TestCase):
    """Verify User Answers 1 & 2: Reranker modes/404 alias error/fallback and ExternalSearchPort DI."""

    def test_cohere_direct_and_gateway_reranker_modes_and_404_error(self) -> None:
        captured_requests: list[tuple[str, dict[str, Any]]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            captured_requests.append((str(request.url), body))
            if body["model"] == "unknown-slug-404":
                return httpx.Response(404, json={"message": "model 'unknown-slug-404' not found"})
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"index": 1, "relevance_score": 0.94},
                        {"index": 0, "relevance_score": 0.21},
                    ]
                },
            )

        mock_client = httpx.Client(transport=httpx.MockTransport(_handler))

        # 1. cohere_direct mode with rerank-v4.0-pro
        direct_reranker = HttpReranker(
            provider="cohere_direct",
            model="rerank-v4.0-pro",
            cohere_api_key="test-cohere",
            http_client=mock_client,
        )
        probe_res = direct_reranker.probe_two_doc_dummy()
        self.assertEqual(probe_res["provider"], "cohere_direct")
        self.assertEqual(probe_res["model"], "rerank-v4.0-pro")
        self.assertEqual(captured_requests[-1][0], "https://api.cohere.com/v2/rerank")

        # 2. gateway mode with cohere/rerank-4-pro unchanged
        gw_reranker = HttpReranker(
            provider="gateway",
            model="cohere/rerank-4-pro",
            gateway_base_url="https://api.portkey.ai/v1",
            gateway_api_key="test-gw",
            http_client=mock_client,
        )
        gw_res = gw_reranker.rerank(
            "query",
            [{"chunk_id": "c0", "text": "doc0"}, {"chunk_id": "c1", "text": "doc1"}],
            top_k=2,
        )
        self.assertEqual(captured_requests[-1][0], "https://api.portkey.ai/v1/rerank")
        self.assertEqual(captured_requests[-1][1]["model"], "cohere/rerank-4-pro")
        self.assertEqual(gw_res[0]["chunk_id"], "c1")

        # 3. 404 unknown-model error names RERANK_PROVIDER, RERANK_MODEL, and alias table
        bad_reranker = HttpReranker(
            provider="cohere_direct",
            model="unknown-slug-404",
            cohere_api_key="test-cohere",
            http_client=mock_client,
        )
        with self.assertRaises(RerankerConfigError) as ctx:
            bad_reranker.probe_two_doc_dummy()
        err_msg = str(ctx.exception)
        self.assertIn("RERANK_PROVIDER='cohere_direct'", err_msg)
        self.assertIn("RERANK_MODEL='unknown-slug-404'", err_msg)
        self.assertIn("rerank-v4.0-pro", err_msg)
        self.assertIn("cohere/rerank-4-pro", err_msg)

        # 4. Explicit optional RERANK_FALLBACK_MODEL logs a warning and succeeds
        fb_reranker = HttpReranker(
            provider="cohere_direct",
            model="unknown-slug-404",
            fallback_model="rerank-v4.0-pro",
            cohere_api_key="test-cohere",
            http_client=mock_client,
        )
        with self.assertLogs("alba_one.retrieval.reranker", level="WARNING") as log_ctx:
            fb_res = fb_reranker.rerank(
                "query",
                [{"chunk_id": "c0", "text": "doc0"}, {"chunk_id": "c1", "text": "doc1"}],
                top_k=1,
            )
        self.assertEqual(fb_res[0]["rerank_model"], "rerank-v4.0-pro")
        self.assertTrue(any("RERANK_FALLBACK_MODEL" in line for line in log_ctx.output))

    def test_fake_reranker_ranks_without_network(self) -> None:
        fake = FakeReranker()
        chunks = [
            {"chunk_id": "c_low", "score": 0.2, "text": "Unrelated topic"},
            {"chunk_id": "c_high", "score": 0.8, "text": "RT-KNT-101 SLA is 4.0 hours"},
        ]
        ranked = fake.rerank("RT-KNT-101 SLA", chunks, top_k=2)
        self.assertEqual(ranked[0]["chunk_id"], "c_high")
        self.assertEqual(len(fake.calls), 1)

    def test_corrective_rag_three_external_search_cases(self) -> None:
        low_graded = GradedChunkSet(
            passed_chunks=[],
            rejected_chunks=[{"chunk_id": "c1", "score": 0.10, "text": "low"}],
            max_score=0.10,
            mean_score=0.10,
            meets_threshold=False,
        )
        guard = RetrieverGuardrailStub()

        # Case (a): Fallback disabled (ALLOW_EXTERNAL_FALLBACK=false) -> insufficient_evidence, port not called
        port_a = FakeExternalSearch(
            [
                ExternalResult(
                    text="External maritime index rose 4%",
                    source_url="https://example.com/maritime",
                    retrieved_at="2026-10-24T00:00:00Z",
                    source_kind="news",
                )
            ]
        )
        res_a = run_corrective_rag(
            query="External Baltic Dry Index today",
            lang="en",
            initial_graded=low_graded,
            retry_retrieve_fn=lambda q: [],
            external_port=port_a,
            guardrail=guard,
            relevance_threshold=0.35,
            allow_external_fallback=False,
        )
        self.assertEqual(res_a.status, "insufficient_evidence")
        self.assertFalse(res_a.external_used)
        self.assertEqual(len(port_a.calls), 0)

        # Case (b): Enabled with results -> external_fallback, marked external=True, PII redacted
        port_b = FakeExternalSearch(
            [
                ExternalResult(
                    text="Tokyo port wind advisory reported by 渡辺 剛 (090-1234-5678).",
                    source_url="https://weather.example.jp/tyo-port",
                    retrieved_at="2026-10-24T02:00:00Z",
                    source_kind="web",
                )
            ]
        )
        res_b = run_corrective_rag(
            query="Tokyo port external wind advisory",
            lang="en",
            initial_graded=low_graded,
            retry_retrieve_fn=lambda q: [],
            external_port=port_b,
            guardrail=guard,
            relevance_threshold=0.35,
            allow_external_fallback=True,
        )
        self.assertEqual(res_b.status, "external_fallback")
        self.assertTrue(res_b.external_used)
        self.assertEqual(len(res_b.chunks), 1)
        self.assertTrue(res_b.chunks[0]["external"])
        self.assertEqual(res_b.chunks[0]["source_url"], "https://weather.example.jp/tyo-port")
        self.assertNotIn("渡辺 剛", res_b.chunks[0]["text"])
        self.assertIn("[PII_PERSON]", res_b.chunks[0]["text"])

        # Case (c): Enabled with empty results (e.g. StubExternalSearchAdapter) -> insufficient_evidence with tried_steps
        port_c = FakeExternalSearch([])
        res_c = run_corrective_rag(
            query="Unknown external topic",
            lang="ja",
            initial_graded=low_graded,
            retry_retrieve_fn=lambda q: [],
            external_port=port_c,
            guardrail=guard,
            relevance_threshold=0.35,
            allow_external_fallback=True,
        )
        self.assertEqual(res_c.status, "insufficient_evidence")
        self.assertFalse(res_c.external_used)
        self.assertEqual(res_c.chunks, [])
        self.assertGreaterEqual(len(res_c.tried_steps), 3)


if __name__ == "__main__":
    unittest.main()
