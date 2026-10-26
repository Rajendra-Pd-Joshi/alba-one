"""Gateway-routed embedding client (`kb/embedder.py`).

Uses `langchain_openai.OpenAIEmbeddings` pointed at `GATEWAY_BASE_URL` with
configured `EMBEDDING_MODEL` (`text-embedding-3-large`) and `EMBEDDING_DIMENSIONS`
(Principle 6: Config-driven models). Also provides a deterministic hash-projection
embedder for offline unit tests and dry-run verification.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from alba_one.gateway.routing import GatewayCallMetadata, build_gateway_headers


class EmbeddingProvider(Protocol):
    """Protocol implemented by both gateway `OpenAIEmbeddings` and deterministic test embedder."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class DeterministicHashEmbedder:
    """# STUB: Deterministic unit-norm vector generator for offline tests and dry-run indexing."""

    def __init__(self, dimensions: int = 1536) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive.")
        self.dimensions = dimensions

    def _vec(self, text: str) -> list[float]:
        raw: list[float] = []
        tokens = text.lower().split() or [text]
        vec = [0.0] * self.dimensions
        for tok in tokens:
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(0, len(digest), 2):
                idx = ((digest[i] << 8) | digest[i + 1]) % self.dimensions
                sign = 1.0 if (digest[i] & 1) == 0 else -1.0
                vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        raw = [round(v / norm, 6) for v in vec]
        return raw

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def create_gateway_embeddings(
    *,
    tenant_id: str,
    embedding_model: str,
    embedding_dimensions: int,
    gateway_provider: str,
    gateway_base_url: str,
    gateway_api_key: str,
    openai_api_key: str,
    extra_headers: dict[str, str] | None = None,
) -> EmbeddingProvider:
    """Create a `langchain_openai.OpenAIEmbeddings` instance routed through the LLM gateway."""
    from langchain_openai import OpenAIEmbeddings
    from pydantic import SecretStr

    metadata = GatewayCallMetadata(
        tenant_id=tenant_id,
        task="kb_embedding",
        prompt_version="embed_v1.0",
    )
    headers = build_gateway_headers(
        provider=gateway_provider,
        gateway_api_key=gateway_api_key,
        metadata=metadata,
        extra_headers=extra_headers,
    )
    api_key_val = openai_api_key if gateway_provider.lower() == "portkey" else gateway_api_key
    return OpenAIEmbeddings(
        model=embedding_model,
        dimensions=embedding_dimensions,
        base_url=gateway_base_url,
        api_key=SecretStr(api_key_val),
        default_headers=headers,
    )
