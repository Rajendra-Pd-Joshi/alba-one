"""Stage 6: Self-RAG Relevance & Post-Generation Support Grader (`retrieval/grader.py`).

Performs:
1. Per-chunk relevance grading (`grade_retrieved_chunks`) comparing each chunk's
   relevance score and lexical/entity overlap against `relevance_threshold`.
2. Post-generation support verification (`check_answer_supported_by_chunks`) verifying
   whether a draft answer/hypothesis is grounded in the retrieved chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from alba_one.kb.fts import tokenize_for_fts


@dataclass(frozen=True)
class GradedChunkSet:
    """Result of Self-RAG per-chunk relevance grading."""

    passed_chunks: list[dict[str, Any]] = field(default_factory=list)
    rejected_chunks: list[dict[str, Any]] = field(default_factory=list)
    max_score: float = 0.0
    mean_score: float = 0.0
    meets_threshold: bool = False


@dataclass(frozen=True)
class SupportCheckResult:
    """Result of Self-RAG post-generation support check."""

    is_supported: bool
    token_overlap_ratio: float
    supporting_chunk_ids: list[str] = field(default_factory=list)
    unsupported_reason: str | None = None


def grade_retrieved_chunks(
    query: str,
    chunks: Sequence[dict[str, Any]],
    *,
    relevance_threshold: float = 0.35,
) -> GradedChunkSet:
    """Grade each chunk against `relevance_threshold` and partition into passed vs rejected."""
    if not chunks:
        return GradedChunkSet(
            passed_chunks=[],
            rejected_chunks=[],
            max_score=0.0,
            mean_score=0.0,
            meets_threshold=False,
        )

    passed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    scores: list[float] = []

    for chk in chunks:
        score = float(chk.get("rerank_score", chk.get("score", 0.0)))
        scores.append(score)
        item = dict(chk)
        item["self_rag_relevant"] = score >= relevance_threshold
        if score >= relevance_threshold:
            passed.append(item)
        else:
            rejected.append(item)

    max_s = max(scores) if scores else 0.0
    mean_s = sum(scores) / len(scores) if scores else 0.0
    return GradedChunkSet(
        passed_chunks=passed,
        rejected_chunks=rejected,
        max_score=round(max_s, 4),
        mean_score=round(mean_s, 4),
        meets_threshold=len(passed) > 0 and max_s >= relevance_threshold,
    )


def check_answer_supported_by_chunks(
    draft_answer: str,
    chunks: Sequence[dict[str, Any]],
    *,
    min_support_ratio: float = 0.25,
) -> SupportCheckResult:
    """Verify that key content tokens in `draft_answer` appear in the cited `chunks`."""
    if not draft_answer.strip() or not chunks:
        return SupportCheckResult(
            is_supported=False,
            token_overlap_ratio=0.0,
            supporting_chunk_ids=[],
            unsupported_reason="Empty draft answer or zero supporting chunks.",
        )

    ans_tokens = set(tokenize_for_fts(draft_answer))
    if not ans_tokens:
        return SupportCheckResult(
            is_supported=False,
            token_overlap_ratio=0.0,
            supporting_chunk_ids=[],
            unsupported_reason="No indexable tokens in draft answer.",
        )

    supporting_ids: list[str] = []
    union_chunk_tokens: set[str] = set()
    for chk in chunks:
        c_tokens = set(tokenize_for_fts(str(chk.get("expanded_text") or chk.get("text") or "")))
        if ans_tokens & c_tokens:
            supporting_ids.append(str(chk.get("chunk_id", "")))
            union_chunk_tokens |= c_tokens

    overlap = len(ans_tokens & union_chunk_tokens) / len(ans_tokens)
    supported = overlap >= min_support_ratio and len(supporting_ids) > 0
    return SupportCheckResult(
        is_supported=supported,
        token_overlap_ratio=round(overlap, 4),
        supporting_chunk_ids=supporting_ids,
        unsupported_reason=None if supported else f"Overlap {overlap:.2f} < {min_support_ratio:.2f}",
    )
