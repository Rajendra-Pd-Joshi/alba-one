"""Stage 8: Reranker (`retrieval/reranker.py`).

Supports two separate, config-driven provider paths:
1. `RERANK_PROVIDER=cohere_direct`: Calls Cohere's v2 rerank endpoint (`https://api.cohere.com/v2/rerank`)
   using `RERANK_MODEL` (default `rerank-v4.0-pro`).
2. `RERANK_PROVIDER=gateway`: Calls `{GATEWAY_BASE_URL}/rerank` passing `RERANK_MODEL` unchanged.

Rules (User Answer 1):
- `RERANK_MODEL` is a free string, never validated against a fixed list.
- If a 404 / unknown-model error occurs, fails with a readable message naming
  `RERANK_PROVIDER`, `RERANK_MODEL`, and the known alias table.
- Never silently falls back to another model. If optional `RERANK_FALLBACK_MODEL`
  (default empty) is set, logs a loud `WARNING` whenever the fallback is used.
- Unit and eval tests use `FakeReranker`; no test calls the live API.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from alba_one.kb.fts import score_fts_match, tokenize_for_fts

logger = logging.getLogger("alba_one.retrieval.reranker")

RERANK_ALIAS_TABLE_TEXT = (
    "Known reranker model identifiers by provider (check your gateway's docs for its exact slug):\n"
    "  - cohere_direct (Cohere v2 API): 'rerank-v4.0-pro' (default), 'rerank-v3.5', 'rerank-multilingual-v3.0'\n"
    "  - gateway (third-party gateways): 'rerank-4-pro', 'cohere/rerank-4-pro', 'cohere/rerank-v4-pro'"
)


class RerankerConfigError(RuntimeError):
    """Raised when the reranker returns 404 / unknown-model or invalid provider config."""


def build_rerank_404_error_message(provider: str, model: str, status_code: int, detail: str = "") -> str:
    """Format a clear error message naming `RERANK_PROVIDER`, `RERANK_MODEL`, and the alias table."""
    return (
        f"Reranker model check failed (HTTP {status_code}) for "
        f"RERANK_PROVIDER='{provider}', RERANK_MODEL='{model}'. {detail}\n"
        f"{RERANK_ALIAS_TABLE_TEXT}"
    )


class RerankerPort(Protocol):
    """Protocol implemented by `HttpReranker` and `FakeReranker`."""

    def rerank(
        self,
        query: str,
        chunks: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]: ...


class FakeReranker:
    """Deterministic fake reranker for unit tests and offline evaluations (never calls external APIs)."""

    def __init__(self, model_name: str = "rerank-v4.0-pro") -> None:
        self.model_name = model_name
        self.calls: list[tuple[str, int]] = []

    def rerank(
        self,
        query: str,
        chunks: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        self.calls.append((query, len(chunks)))
        if not chunks:
            return []

        scored: list[dict[str, Any]] = []
        for chk in chunks:
            text = str(chk.get("expanded_text") or chk.get("text") or "")
            tok_str = " ".join(tokenize_for_fts(text))
            lex_boost = score_fts_match(query, tok_str)
            base_score = float(chk.get("score", 0.0))
            rerank_score = round(min(1.0, 0.55 * base_score + 0.45 * lex_boost), 4)
            item = dict(chk)
            item["rerank_score"] = rerank_score
            item["rerank_model"] = self.model_name
            item["score"] = rerank_score
            scored.append(item)

        scored.sort(key=lambda x: (-x["rerank_score"], str(x.get("chunk_id", ""))))
        return scored[: max(1, top_k)]


class HttpReranker:
    """Production reranker supporting `cohere_direct` (`/v2/rerank`) and `gateway` (`/rerank`)."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        cohere_api_key: str = "",
        gateway_base_url: str = "",
        gateway_api_key: str = "",
        fallback_model: str = "",
        cohere_v2_url: str = "https://api.cohere.com/v2/rerank",
        timeout_seconds: float = 15.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        norm_provider = provider.strip().lower()
        if norm_provider not in ("cohere_direct", "gateway"):
            raise RerankerConfigError(
                f"Invalid RERANK_PROVIDER='{provider}'. Must be 'cohere_direct' or 'gateway'."
            )
        if not model.strip():
            raise RerankerConfigError("RERANK_MODEL cannot be empty.")

        self.provider = norm_provider
        self.model = model.strip()
        self.cohere_api_key = cohere_api_key
        self.gateway_base_url = gateway_base_url.rstrip("/")
        self.gateway_api_key = gateway_api_key
        self.fallback_model = fallback_model.strip()
        self.cohere_v2_url = cohere_v2_url
        self.timeout_seconds = timeout_seconds
        self._client = http_client

    def _call_cohere_direct(
        self, model_name: str, query: str, docs: list[str], top_n: int
    ) -> list[dict[str, Any]]:
        """Path 1: Call Cohere v2 rerank API directly."""
        headers = {
            "Authorization": f"Bearer {self.cohere_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {"model": model_name, "query": query, "documents": docs, "top_n": top_n}
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_after = self._client is None
        try:
            resp = client.post(self.cohere_v2_url, headers=headers, json=body)
        finally:
            if close_after:
                client.close()
        return self._parse_response(resp, model_name)

    def _call_gateway(
        self, model_name: str, query: str, docs: list[str], top_n: int
    ) -> list[dict[str, Any]]:
        """Path 2: Call the LLM gateway's `/rerank` endpoint with `RERANK_MODEL` unchanged."""
        url = f"{self.gateway_base_url}/rerank"
        headers = {
            "Authorization": f"Bearer {self.gateway_api_key}",
            "x-portkey-api-key": self.gateway_api_key,
            "Content-Type": "application/json",
        }
        body = {"model": model_name, "query": query, "documents": docs, "top_n": top_n}
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_after = self._client is None
        try:
            resp = client.post(url, headers=headers, json=body)
        finally:
            if close_after:
                client.close()
        return self._parse_response(resp, model_name)

    def _parse_response(self, resp: httpx.Response, model_name: str) -> list[dict[str, Any]]:
        if resp.status_code in (400, 404, 422):
            raise RerankerConfigError(
                build_rerank_404_error_message(
                    self.provider, model_name, resp.status_code, resp.text[:200]
                )
            )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not isinstance(results, list):
            raise RerankerConfigError("Malformed rerank response: missing 'results' list.")
        return results

    def _invoke_with_optional_fallback(
        self, query: str, docs: list[str], top_n: int
    ) -> tuple[list[dict[str, Any]], str]:
        caller = self._call_cohere_direct if self.provider == "cohere_direct" else self._call_gateway
        try:
            return caller(self.model, query, docs, top_n), self.model
        except Exception as primary_exc:
            if not self.fallback_model:
                raise
            logger.warning(
                f"Primary reranker '{self.model}' failed ({primary_exc}); "
                f"using explicit RERANK_FALLBACK_MODEL='{self.fallback_model}'."
            )
            return caller(self.fallback_model, query, docs, top_n), self.fallback_model

    def rerank(
        self,
        query: str,
        chunks: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []
        docs = [str(c.get("expanded_text") or c.get("text") or "") for c in chunks]
        top_n = min(len(docs), max(1, top_k))
        raw_results, used_model = self._invoke_with_optional_fallback(query, docs, top_n)

        reranked: list[dict[str, Any]] = []
        for entry in raw_results:
            idx = int(entry["index"])
            rel_score = float(entry.get("relevance_score", 0.0))
            item = dict(chunks[idx])
            item["rerank_score"] = round(rel_score, 4)
            item["rerank_model"] = used_model
            item["score"] = round(rel_score, 4)
            reranked.append(item)

        reranked.sort(key=lambda x: -float(x["rerank_score"]))
        return reranked[:top_n]

    def probe_two_doc_dummy(self) -> dict[str, Any]:
        """Startup health probe reranking a 2-document dummy query with the configured model."""
        dummy_chunks = [
            {"chunk_id": "probe_1", "text": "東京港大井第3バースの定温コンテナ配送SLAは4時間以内。"},
            {"chunk_id": "probe_2", "text": "Mechanical keyboard switch actuation force table."},
        ]
        res = self.rerank("東京港大井バースの配送SLA", dummy_chunks, top_k=2)
        return {
            "provider": self.provider,
            "model": self.model,
            "top_chunk_id": res[0]["chunk_id"] if res else None,
        }
