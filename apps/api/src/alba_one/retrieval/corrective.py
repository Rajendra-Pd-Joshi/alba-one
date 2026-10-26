"""Stage 7: Corrective RAG (`retrieval/corrective.py`).

Implements User Answer 2 & Phase 3 Requirement 7:
- Receives `ExternalSearchPort` strictly via dependency injection (constructor/argument),
  never by importing a concrete external search implementation.
- If initial Self-RAG graded relevance is below `relevance_threshold`:
  1. Rewrites the query once (`retry_count = 1`) and re-runs hybrid retrieval + reranking + grading.
  2. If relevance is STILL below `relevance_threshold`:
     - If `allow_external_fallback=True`, calls `external_port.search(query, lang, max_results)`.
     - Passes external results through `RetrieverGuardrailStub.filter_external_results(...)`
       (PII redaction + prompt-injection scan).
     - If guardrail-cleaned external results are non-empty, marks the outcome `status="external_fallback"`
       with `external=True` and preserves `source_url` citations.
     - If `allow_external_fallback=False` OR the port returns `[]`, returns an explicit
       `status="insufficient_evidence"` with the complete `tried_steps` audit trail.
- Never invents evidence or silently continues with low-relevance chunks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from alba_one.retrieval.grader import GradedChunkSet, grade_retrieved_chunks
from alba_one.retrieval.guardrail_stub import RetrieverGuardrailStub
from alba_one.retrieval.ports import ExternalResult, ExternalSearchPort

CorrectiveOutcomeStatus = Literal["grounded_kb", "external_fallback", "insufficient_evidence"]


@dataclass(frozen=True)
class CorrectiveRAGResult:
    """Result of Corrective RAG evaluation, retry, and optional external search fallback."""

    status: CorrectiveOutcomeStatus
    chunks: list[dict[str, Any]] = field(default_factory=list)
    external_results: list[ExternalResult] = field(default_factory=list)
    external_used: bool = False
    retry_performed: bool = False
    tried_steps: list[str] = field(default_factory=list)
    guardrail_events: list[dict[str, Any]] = field(default_factory=list)


def run_corrective_rag(
    *,
    query: str,
    lang: str,
    initial_graded: GradedChunkSet,
    retry_retrieve_fn: Callable[[str], list[dict[str, Any]]],
    external_port: ExternalSearchPort,
    guardrail: RetrieverGuardrailStub,
    relevance_threshold: float = 0.35,
    allow_external_fallback: bool = True,
    max_external_results: int = 3,
) -> CorrectiveRAGResult:
    """Execute Corrective RAG: 1 rewrite retry -> optional `ExternalSearchPort` -> `insufficient_evidence`."""
    tried_steps: list[str] = [
        f"initial_kb_retrieval(max_score={initial_graded.max_score}, passed={len(initial_graded.passed_chunks)})"
    ]

    if initial_graded.meets_threshold:
        return CorrectiveRAGResult(
            status="grounded_kb",
            chunks=initial_graded.passed_chunks,
            external_results=[],
            external_used=False,
            retry_performed=False,
            tried_steps=tried_steps,
        )

    # Step 1: Rewrite once and retry internal KB retrieval
    retry_query = (
        f"{query} 業務規定 数値条件 バース 配送 要員 モデル"
        if lang == "ja"
        else f"{query} operational specification constraints SLA berth route staff model"
    )
    retried_raw_chunks = retry_retrieve_fn(retry_query)
    retried_graded = grade_retrieved_chunks(
        retry_query,
        retried_raw_chunks,
        relevance_threshold=relevance_threshold,
    )
    tried_steps.append(
        f"rewrite_retry_1(query='{retry_query}', max_score={retried_graded.max_score}, passed={len(retried_graded.passed_chunks)})"
    )

    if retried_graded.meets_threshold:
        return CorrectiveRAGResult(
            status="grounded_kb",
            chunks=retried_graded.passed_chunks,
            external_results=[],
            external_used=False,
            retry_performed=True,
            tried_steps=tried_steps,
        )

    # Step 2: Check if external fallback is allowed by configuration
    if not allow_external_fallback:
        tried_steps.append("external_fallback_skipped(ALLOW_EXTERNAL_FALLBACK=false)")
        return CorrectiveRAGResult(
            status="insufficient_evidence",
            chunks=[],
            external_results=[],
            external_used=False,
            retry_performed=True,
            tried_steps=tried_steps,
        )

    # Step 3: Call injected ExternalSearchPort and pass results through retriever guardrail
    raw_ext = external_port.search(query=query, lang=lang, max_results=max_external_results)
    clean_ext, ext_stats = guardrail.filter_external_results(raw_ext)
    tried_steps.append(
        f"external_search_port(raw={len(raw_ext)}, passed_guardrail={len(clean_ext)})"
    )

    if clean_ext:
        ext_as_chunks = [
            {
                "chunk_id": f"ext_{idx + 1}",
                "text": item.text,
                "expanded_text": item.text,
                "score": 0.75,
                "source_table": f"external:{item.source_kind}",
                "source_url": item.source_url,
                "retrieved_at": item.retrieved_at,
                "external": True,
                "lang": lang,
                "entity_ids": [],
                "acl_tags": [],
            }
            for idx, item in enumerate(clean_ext)
        ]
        return CorrectiveRAGResult(
            status="external_fallback",
            chunks=ext_as_chunks,
            external_results=clean_ext,
            external_used=True,
            retry_performed=True,
            tried_steps=tried_steps,
            guardrail_events=ext_stats.events,
        )

    tried_steps.append("insufficient_evidence(no_grounded_kb_or_external_results)")
    return CorrectiveRAGResult(
        status="insufficient_evidence",
        chunks=[],
        external_results=[],
        external_used=False,
        retry_performed=True,
        tried_steps=tried_steps,
        guardrail_events=ext_stats.events,
    )
