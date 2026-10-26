"""Stage 4: Hybrid Retrieval with Reciprocal Rank Fusion (RRF) & Parent-Child Expansion (`retrieval/hybrid.py`).

Executes:
1. Dense retrieval against Pinecone vector index (filtered by `tenant_id`, `acl_tags`, and `valid_from/valid_to`).
2. Keyword retrieval against on-prem PostgreSQL FTS (`kb_chunks.tokenized_text` with Japanese tokenization).
3. Reciprocal Rank Fusion (`reciprocal_rank_fusion`, default `rrf_k=60`) across all query variants.
4. Parent-child context expansion (`expand_parent_context`) attaching `parent_text` to child chunks.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Literal

from alba_one.kb.fts import score_fts_match
from alba_one.kb.indexer import KnowledgeBaseIndexer

RetrievalMode = Literal["hybrid", "dense_only", "keyword_only"]


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]],
    *,
    rrf_k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ordered chunk ID lists using Reciprocal Rank Fusion (RRF).

    Score formula per chunk `d` across lists `L`:
        RRF(d) = sum_{L} 1.0 / (rrf_k + rank_L(d))
    where `rank_L(d)` is 1-indexed. Normalized to [0, 1] for downstream confidence scoring.
    """
    if rrf_k <= 0:
        raise ValueError("rrf_k must be a positive integer.")
    if not ranked_lists:
        return []

    raw_scores: dict[str, float] = {}
    for rlist in ranked_lists:
        seen_in_list: set[str] = set()
        for rank_idx, chunk_id in enumerate(rlist, start=1):
            if chunk_id in seen_in_list:
                continue
            seen_in_list.add(chunk_id)
            raw_scores[chunk_id] = raw_scores.get(chunk_id, 0.0) + (1.0 / (rrf_k + rank_idx))

    if not raw_scores:
        return []

    max_possible = len(ranked_lists) * (1.0 / (rrf_k + 1))
    normalized = [
        (cid, round(min(1.0, score / max(1e-9, max_possible)), 4))
        for cid, score in raw_scores.items()
    ]
    normalized.sort(key=lambda item: (-item[1], item[0]))
    return normalized


def _is_within_validity_window(
    valid_from: str | None,
    valid_to: str | None,
    reference_iso: str | None = None,
) -> bool:
    """Verify whether a chunk's `[valid_from, valid_to]` window covers `reference_iso`."""
    if not reference_iso:
        return True
    if valid_from and valid_from > reference_iso:
        return False
    if valid_to and valid_to.strip() and valid_to < reference_iso:
        return False
    return True


def _dense_cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, min(1.0, (dot / (na * nb) + 1.0) / 2.0))


def expand_parent_context(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach parent context (`expanded_text`) when a chunk carries `parent_chunk_id` / `parent_text`."""
    expanded: list[dict[str, Any]] = []
    for chk in chunks:
        item = dict(chk)
        meta = item.get("metadata") or {}
        parent_text = item.get("parent_text") or meta.get("parent_text")
        if parent_text and item.get("parent_chunk_id"):
            item["expanded_text"] = f"{parent_text}\n[Matched Segment] {item['text']}"
        else:
            item["expanded_text"] = item["text"]
        expanded.append(item)
    return expanded


def run_hybrid_retrieval(
    indexer: KnowledgeBaseIndexer,
    *,
    tenant_id: str,
    caller_role: str,
    queries: Sequence[str],
    top_k: int = 8,
    mode: RetrievalMode = "hybrid",
    reference_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Run dense + Japanese FTS retrieval across `queries`, fuse with RRF, and expand parent context."""
    if not queries or top_k <= 0:
        return []

    allowed_acl = {f"role:{caller_role.strip().lower()}"}
    ns_vectors = getattr(indexer.vectors, "namespaces", {}).get(tenant_id, {})

    ranked_lists: list[list[str]] = []
    best_lexical_by_chunk: dict[str, float] = {}
    best_dense_by_chunk: dict[str, float] = {}

    for q in queries:
        q_vec = indexer.embedder.embed_query(q)
        dense_candidates: list[tuple[float, str]] = []
        fts_candidates: list[tuple[float, str]] = []

        for chunk_id, (vec, meta) in ns_vectors.items():
            if meta.get("tenant_id") != tenant_id:
                continue
            chunk_acls = set(meta.get("acl_tags", []))
            if chunk_acls and not (chunk_acls & allowed_acl):
                continue
            if not _is_within_validity_window(
                meta.get("valid_from"),
                meta.get("valid_to"),
                reference_iso,
            ):
                continue

            d_score = _dense_cosine(q_vec, vec)
            tok_str = indexer.onprem.tokenized_by_chunk.get(chunk_id, "")
            k_score = score_fts_match(q, tok_str)

            best_dense_by_chunk[chunk_id] = max(best_dense_by_chunk.get(chunk_id, 0.0), d_score)
            best_lexical_by_chunk[chunk_id] = max(best_lexical_by_chunk.get(chunk_id, 0.0), k_score)

            dense_candidates.append((d_score, chunk_id))
            if k_score > 0.0:
                fts_candidates.append((k_score, chunk_id))

        dense_candidates.sort(key=lambda x: (-x[0], x[1]))
        fts_candidates.sort(key=lambda x: (-x[0], x[1]))

        if mode in ("hybrid", "dense_only") and dense_candidates:
            ranked_lists.append([cid for _, cid in dense_candidates[: top_k * 2]])
        if mode in ("hybrid", "keyword_only") and fts_candidates:
            ranked_lists.append([cid for _, cid in fts_candidates[: top_k * 2]])

    fused = reciprocal_rank_fusion(ranked_lists, rrf_k=60)
    results: list[dict[str, Any]] = []

    for chunk_id, rrf_score in fused[:top_k]:
        chk = indexer.onprem.chunks.get(chunk_id)
        if chk is None or chk.tenant_id != tenant_id:
            continue
        lex = best_lexical_by_chunk.get(chunk_id, 0.0)
        den = best_dense_by_chunk.get(chunk_id, 0.0)
        if mode == "keyword_only":
            combined_score = round(lex, 4)
        elif mode == "dense_only":
            combined_score = round(den, 4)
        else:
            combined_score = round(min(1.0, 0.45 * rrf_score + 0.40 * lex + 0.15 * den), 4)

        results.append(
            {
                "chunk_id": chk.chunk_id,
                "document_id": chk.document_id,
                "tenant_id": chk.tenant_id,
                "text": chk.text,
                "score": combined_score,
                "rrf_score": rrf_score,
                "lexical_score": round(lex, 4),
                "dense_score": round(den, 4),
                "source_table": chk.source_table,
                "entity_type": chk.entity_type,
                "entity_ids": list(chk.entity_ids),
                "acl_tags": list(chk.acl_tags),
                "lang": chk.lang,
                "parent_chunk_id": chk.parent_chunk_id,
                "metadata": dict(chk.metadata),
            }
        )

    results.sort(key=lambda x: (-x["score"], x["chunk_id"]))
    return expand_parent_context(results)
