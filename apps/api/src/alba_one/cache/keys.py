"""Pure cache-key construction and caching eligibility rules (stdlib only).

Enforces:
1. Key = tenant_id + model + prompt_version + normalised input + retrieval-set hash.
2. Strict tenant isolation (Principle 8): every cache key is prefixed with `alba:llm_cache:{tenant_id}:`.
3. Safety policy (Principle 4 & Phase 1.5): NEVER cache HITL responses or side-effecting tool results.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_prompt_input(raw_input: str) -> str:
    """Normalize Unicode (NFKC) and collapse runs of whitespace for deterministic hashing."""
    normalized = unicodedata.normalize("NFKC", raw_input or "")
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def compute_retrieval_set_hash(chunk_ids: Sequence[str] | None) -> str:
    """Compute a deterministic SHA-256 hex digest over sorted unique retrieval chunk IDs."""
    if not chunk_ids:
        return hashlib.sha256(b"empty_retrieval_set").hexdigest()[:16]
    cleaned = sorted({c.strip() for c in chunk_ids if c and c.strip()})
    if not cleaned:
        return hashlib.sha256(b"empty_retrieval_set").hexdigest()[:16]
    joined = "|".join(cleaned)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def build_llm_cache_key(
    *,
    tenant_id: str,
    model: str,
    prompt_version: str,
    raw_input: str,
    retrieval_chunk_ids: Sequence[str] | None = None,
) -> str:
    """Build a tenant-isolated Redis key for exact-match LLM response caching.

    Format:
        `alba:llm_cache:{tenant_id}:{model}:{prompt_version}:{input_hash}:{retrieval_hash}`
    """
    t_id = tenant_id.strip()
    m_id = model.strip()
    p_ver = prompt_version.strip()
    if not t_id:
        raise ValueError("tenant_id is required to build an LLM cache key (Principle 8).")
    if not m_id:
        raise ValueError("model is required to build an LLM cache key.")
    if not p_ver:
        raise ValueError("prompt_version is required to build an LLM cache key.")

    norm_input = normalize_prompt_input(raw_input)
    input_hash = hashlib.sha256(norm_input.encode("utf-8")).hexdigest()[:24]
    ret_hash = compute_retrieval_set_hash(retrieval_chunk_ids)
    return f"alba:llm_cache:{t_id}:{m_id}:{p_ver}:{input_hash}:{ret_hash}"


def should_cache_llm_call(
    *,
    is_hitl_response: bool = False,
    has_side_effecting_tools: bool = False,
) -> bool:
    """Return False if the call involves human-in-the-loop approval or side-effecting tools."""
    if is_hitl_response or has_side_effecting_tools:
        return False
    return True
