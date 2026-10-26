"""Redis exact-match LLM response cache enforcing tenant isolation and HITL/tool exclusions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from alba_one.cache.keys import build_llm_cache_key, should_cache_llm_call


class RedisKeyValueProtocol(Protocol):
    """Minimal key-value interface compatible with `redis.Redis` and `fakeredis.FakeRedis`."""

    def get(self, name: str) -> bytes | str | None: ...
    def setex(self, name: str, time: int, value: str) -> Any: ...


class ExactMatchLLMCache:
    """Exact-match LLM cache keyed by `(tenant_id, model, prompt_version, input, retrieval_set)`.

    Never caches human-in-the-loop (HITL) responses or side-effecting tool results.
    """

    def __init__(self, redis_client: RedisKeyValueProtocol, ttl_seconds: int = 86400) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer.")
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    def get(
        self,
        *,
        tenant_id: str,
        model: str,
        prompt_version: str,
        raw_input: str,
        retrieval_chunk_ids: Sequence[str] | None = None,
        is_hitl_response: bool = False,
        has_side_effecting_tools: bool = False,
    ) -> dict[str, Any] | None:
        """Look up a cached LLM response; returns None on miss or if ineligible for caching."""
        if not should_cache_llm_call(
            is_hitl_response=is_hitl_response,
            has_side_effecting_tools=has_side_effecting_tools,
        ):
            return None

        key = build_llm_cache_key(
            tenant_id=tenant_id,
            model=model,
            prompt_version=prompt_version,
            raw_input=raw_input,
            retrieval_chunk_ids=retrieval_chunk_ids,
        )
        raw = self._redis.get(key)
        if raw is None:
            return None
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        data = json.loads(text)
        if isinstance(data, dict) and data.get("tenant_id") == tenant_id:
            return data
        return None

    def put(
        self,
        *,
        tenant_id: str,
        model: str,
        prompt_version: str,
        raw_input: str,
        response_payload: dict[str, Any],
        retrieval_chunk_ids: Sequence[str] | None = None,
        is_hitl_response: bool = False,
        has_side_effecting_tools: bool = False,
        ttl_override: int | None = None,
    ) -> bool:
        """Store an LLM response in Redis if eligible; returns True if stored, False if skipped."""
        if not should_cache_llm_call(
            is_hitl_response=is_hitl_response,
            has_side_effecting_tools=has_side_effecting_tools,
        ):
            return False

        key = build_llm_cache_key(
            tenant_id=tenant_id,
            model=model,
            prompt_version=prompt_version,
            raw_input=raw_input,
            retrieval_chunk_ids=retrieval_chunk_ids,
        )
        envelope = {
            "tenant_id": tenant_id,
            "model": model,
            "prompt_version": prompt_version,
            "payload": response_payload,
        }
        ttl = ttl_override if ttl_override is not None else self._ttl_seconds
        self._redis.setex(key, ttl, json.dumps(envelope, ensure_ascii=False))
        return True
