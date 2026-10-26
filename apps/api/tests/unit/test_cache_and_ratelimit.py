"""Unit tests for Redis exact-match LLM cache and token-bucket rate limiter.

Uses `fakeredis.FakeRedis` automatically when installed on the developer machine,
and falls back to a faithful in-memory Redis protocol double when running in an
environment without `fakeredis` pre-installed, while testing the exact same
`ExactMatchLLMCache` and `TokenBucketRateLimiter` classes.
"""

from __future__ import annotations

import importlib.util as _ilu, pathlib as _pl, sys as _sys
_spec = _ilu.spec_from_file_location('_bootstrap', _pl.Path(__file__).with_name('_bootstrap.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)

import unittest
from typing import Any

from alba_one.cache.keys import (
    build_llm_cache_key,
    compute_retrieval_set_hash,
    should_cache_llm_call,
)
from alba_one.cache.llm_cache import ExactMatchLLMCache
from alba_one.cache.rate_limit import (
    TOKEN_BUCKET_LUA_SCRIPT,
    TokenBucketRateLimiter,
    build_rate_limit_key,
)

try:
    import fakeredis  # type: ignore[import-not-found]

    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False


class InMemoryRedisDouble:
    """Minimal Redis protocol implementation for offline stdlib `unittest` execution."""

    def __init__(self) -> None:
        self.kv: dict[str, tuple[str, int]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}

    def get(self, name: str) -> str | None:
        item = self.kv.get(name)
        return item[0] if item else None

    def setex(self, name: str, time: int, value: str) -> bool:
        self.kv[name] = (value, time)
        self.ttls[name] = time
        return True

    def hmget(self, name: str, keys: list[str]) -> list[str | None]:
        bucket = self.hashes.get(name, {})
        return [bucket.get(k) for k in keys]

    def hset(self, name: str, mapping: dict[str, Any]) -> int:
        bucket = self.hashes.setdefault(name, {})
        for k, v in mapping.items():
            bucket[k] = str(v)
        return len(mapping)

    def expire(self, name: str, time: int) -> bool:
        self.ttls[name] = time
        return True

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        raise RuntimeError("Lua runtime not loaded in stdlib double; triggers hash fallback")


def _make_redis_client() -> Any:
    if HAS_FAKEREDIS:
        return fakeredis.FakeRedis(decode_responses=True)
    return InMemoryRedisDouble()


class TestCacheAndRateLimit(unittest.TestCase):
    """Verify exact-match LLM cache rules and per-tenant/user/tool token bucket limits."""

    def test_cache_key_is_tenant_isolated_and_order_independent_for_chunks(self) -> None:
        k1 = build_llm_cache_key(
            tenant_id="tenant_a",
            model="gpt-4o-2024-08-06",
            prompt_version="v1.0",
            raw_input="  アルバ・オーロラ号の着岸優先順位は？ ",
            retrieval_chunk_ids=["chunk_2", "chunk_1"],
        )
        k2 = build_llm_cache_key(
            tenant_id="tenant_a",
            model="gpt-4o-2024-08-06",
            prompt_version="v1.0",
            raw_input="アルバ・オーロラ号の着岸優先順位は?",
            retrieval_chunk_ids=["chunk_1", "chunk_2"],
        )
        k_other_tenant = build_llm_cache_key(
            tenant_id="tenant_b",
            model="gpt-4o-2024-08-06",
            prompt_version="v1.0",
            raw_input="アルバ・オーロラ号の着岸優先順位は?",
            retrieval_chunk_ids=["chunk_1", "chunk_2"],
        )
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k_other_tenant)
        self.assertEqual(
            compute_retrieval_set_hash(["c1", "c2"]),
            compute_retrieval_set_hash(["c2", "c1", "c1"]),
        )

    def test_never_cache_hitl_or_side_effecting_tool_results(self) -> None:
        self.assertTrue(should_cache_llm_call(is_hitl_response=False, has_side_effecting_tools=False))
        self.assertFalse(should_cache_llm_call(is_hitl_response=True, has_side_effecting_tools=False))
        self.assertFalse(should_cache_llm_call(is_hitl_response=False, has_side_effecting_tools=True))

        client = _make_redis_client()
        cache = ExactMatchLLMCache(client, ttl_seconds=3600)

        stored_hitl = cache.put(
            tenant_id="tenant_alba_demo",
            model="gpt-4o-2024-08-06",
            prompt_version="v1",
            raw_input="approve berth B3",
            response_payload={"verdict": "approve"},
            is_hitl_response=True,
        )
        self.assertFalse(stored_hitl)

        stored_side_effect = cache.put(
            tenant_id="tenant_alba_demo",
            model="gpt-4o-2024-08-06",
            prompt_version="v1",
            raw_input="dispatch truck VH-REEFER-08",
            response_payload={"dispatched": True},
            has_side_effecting_tools=True,
        )
        self.assertFalse(stored_side_effect)

        stored_ok = cache.put(
            tenant_id="tenant_alba_demo",
            model="gpt-4o-2024-08-06",
            prompt_version="v1",
            raw_input="compare options A and B",
            response_payload={"options": ["A", "B"]},
            retrieval_chunk_ids=["chunk_synth_001"],
        )
        self.assertTrue(stored_ok)

        hit = cache.get(
            tenant_id="tenant_alba_demo",
            model="gpt-4o-2024-08-06",
            prompt_version="v1",
            raw_input="compare options A and B",
            retrieval_chunk_ids=["chunk_synth_001"],
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["payload"], {"options": ["A", "B"]})

        # Cross-tenant lookup must miss
        cross_hit = cache.get(
            tenant_id="tenant_other",
            model="gpt-4o-2024-08-06",
            prompt_version="v1",
            raw_input="compare options A and B",
            retrieval_chunk_ids=["chunk_synth_001"],
        )
        self.assertIsNone(cross_hit)

    def test_token_bucket_rate_limiter_scopes_and_refill(self) -> None:
        self.assertIn("HMGET", TOKEN_BUCKET_LUA_SCRIPT)
        self.assertEqual(
            build_rate_limit_key(scope="tenant", tenant_id="t1"),
            "alba:rl:tenant:t1",
        )
        self.assertEqual(
            build_rate_limit_key(scope="user", tenant_id="t1", subject_id="u1"),
            "alba:rl:user:t1:u1",
        )
        self.assertEqual(
            build_rate_limit_key(scope="tool", tenant_id="t1", subject_id="sql_query"),
            "alba:rl:tool:t1:sql_query",
        )

        now = 1000.0
        client = _make_redis_client()
        limiter = TokenBucketRateLimiter(client, clock=lambda: now)

        # Burst capacity = 2, RPM = 60 (1 token/sec)
        d1 = limiter.check(scope="user", tenant_id="t1", subject_id="u1", capacity=2, rpm=60)
        d2 = limiter.check(scope="user", tenant_id="t1", subject_id="u1", capacity=2, rpm=60)
        d3 = limiter.check(scope="user", tenant_id="t1", subject_id="u1", capacity=2, rpm=60)

        self.assertTrue(d1.allowed)
        self.assertTrue(d2.allowed)
        self.assertFalse(d3.allowed)
        self.assertGreaterEqual(d3.retry_after_seconds, 1)

        # Advance injectable clock by 1.5 seconds -> 1.5 tokens refilled -> allowed again
        now += 1.5
        d4 = limiter.check(scope="user", tenant_id="t1", subject_id="u1", capacity=2, rpm=60)
        self.assertTrue(d4.allowed)


if __name__ == "__main__":
    unittest.main()
