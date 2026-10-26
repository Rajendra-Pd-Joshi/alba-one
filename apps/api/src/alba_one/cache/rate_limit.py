"""Token-bucket rate limiter (Redis Lua script + pure injectable-clock engine).

Supports three granular scopes (all tenant-isolated):
1. Per-tenant (`alba:rl:tenant:{tenant_id}`)
2. Per-user (`alba:rl:user:{tenant_id}:{user_id}`)
3. Per-tool (`alba:rl:tool:{tenant_id}:{tool_name}`)
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

# Atomic Redis Lua script implementing a token-bucket rate limiter.
# KEYS[1] = bucket hash key
# ARGV[1] = capacity (max burst tokens)
# ARGV[2] = refill_rate_per_sec (tokens added per second)
# ARGV[3] = now_epoch_seconds (float)
# ARGV[4] = requested_tokens (int, typically 1)
# Returns: {allowed (1 or 0), remaining_tokens (float), retry_after_seconds (int)}
TOKEN_BUCKET_LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil or last_refill == nil then
    tokens = capacity
    last_refill = now
else
    local elapsed = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + elapsed * refill_rate)
    last_refill = now
end

local allowed = 0
local retry_after = 0

if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
else
    local deficit = requested - tokens
    retry_after = math.ceil(deficit / refill_rate)
end

local ttl = math.max(60, math.ceil((capacity / refill_rate) * 2))
redis.call("HMSET", key, "tokens", tokens, "last_refill", last_refill)
redis.call("EXPIRE", key, ttl)

return {allowed, tostring(tokens), retry_after}
"""


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a token-bucket check."""

    allowed: bool
    scope_key: str
    remaining_tokens: float
    retry_after_seconds: int


class SyncRedisHashLike(Protocol):
    """Minimal protocol implemented by both `redis.Redis` and `fakeredis.FakeRedis`."""

    def hmget(self, name: str, keys: list[str]) -> list[Any]: ...
    def hset(self, name: str, mapping: dict[str, Any]) -> Any: ...
    def expire(self, name: str, time: int) -> Any: ...
    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any: ...


def build_rate_limit_key(
    *,
    scope: str,
    tenant_id: str,
    subject_id: str | None = None,
) -> str:
    """Build a tenant-scoped Redis key for rate limiting (`tenant`, `user`, or `tool`)."""
    t_id = tenant_id.strip()
    if not t_id:
        raise ValueError("tenant_id is required for rate limit keys (Principle 8).")
    if scope == "tenant":
        return f"alba:rl:tenant:{t_id}"
    if scope in ("user", "tool"):
        if not subject_id or not subject_id.strip():
            raise ValueError(f"subject_id is required when scope='{scope}'.")
        return f"alba:rl:{scope}:{t_id}:{subject_id.strip()}"
    raise ValueError(f"Unsupported rate limit scope '{scope}'. Must be 'tenant', 'user', or 'tool'.")


def evaluate_token_bucket_step(
    *,
    current_tokens: float | None,
    last_refill: float | None,
    capacity: int,
    rpm: int,
    now: float,
    requested: int = 1,
) -> tuple[bool, float, float, int]:
    """Pure mathematical step of the token-bucket algorithm (mirrors `TOKEN_BUCKET_LUA_SCRIPT`).

    Returns `(allowed, new_tokens, new_last_refill, retry_after_seconds)`.
    """
    if capacity <= 0 or rpm <= 0:
        raise ValueError("capacity and rpm must be positive integers.")
    refill_rate = rpm / 60.0
    if current_tokens is None or last_refill is None:
        tokens = float(capacity)
    else:
        elapsed = max(0.0, now - last_refill)
        tokens = min(float(capacity), current_tokens + elapsed * refill_rate)

    if tokens >= requested:
        return True, round(tokens - requested, 6), now, 0

    deficit = requested - tokens
    retry_after = int(math.ceil(deficit / refill_rate))
    return False, round(tokens, 6), now, max(1, retry_after)


class TokenBucketRateLimiter:
    """Redis token-bucket rate limiter using `TOKEN_BUCKET_LUA_SCRIPT` with hash fallback."""

    def __init__(
        self,
        redis_client: SyncRedisHashLike,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis_client
        self._clock = clock

    def check(
        self,
        *,
        scope: str,
        tenant_id: str,
        capacity: int,
        rpm: int,
        subject_id: str | None = None,
        requested: int = 1,
    ) -> RateLimitDecision:
        """Attempt to consume `requested` tokens from the specified bucket."""
        key = build_rate_limit_key(scope=scope, tenant_id=tenant_id, subject_id=subject_id)
        now = self._clock()
        refill_rate = rpm / 60.0

        try:
            res = self._redis.eval(
                TOKEN_BUCKET_LUA_SCRIPT,
                1,
                key,
                capacity,
                refill_rate,
                now,
                requested,
            )
            allowed = bool(int(res[0]))
            remaining = float(res[1])
            retry_after = int(res[2])
            return RateLimitDecision(
                allowed=allowed,
                scope_key=key,
                remaining_tokens=remaining,
                retry_after_seconds=retry_after,
            )
        except Exception:
            # Fallback if fakeredis is installed without lupa Lua runtime
            raw_vals = self._redis.hmget(key, ["tokens", "last_refill"])
            cur_tok = float(raw_vals[0]) if raw_vals and raw_vals[0] is not None else None
            last_ref = float(raw_vals[1]) if raw_vals and raw_vals[1] is not None else None
            allowed, new_tokens, new_last, retry_after = evaluate_token_bucket_step(
                current_tokens=cur_tok,
                last_refill=last_ref,
                capacity=capacity,
                rpm=rpm,
                now=now,
                requested=requested,
            )
            ttl = max(60, int(math.ceil((capacity / refill_rate) * 2)))
            self._redis.hset(key, mapping={"tokens": str(new_tokens), "last_refill": str(new_last)})
            self._redis.expire(key, ttl)
            return RateLimitDecision(
                allowed=allowed,
                scope_key=key,
                remaining_tokens=new_tokens,
                retry_after_seconds=retry_after,
            )
