"""Four chunking strategies for the ALBA ONE knowledge base (`kb/chunkers.py`).

Implements and compares:
1. `recursive_ja`: Recursive character splitting respecting Japanese sentence boundaries (`。`, `！`, `？`, `\n`).
2. `semantic`: Sentence-level semantic shift chunking using character/token n-gram cosine similarity (or an injected embedding similarity callable).
3. `parent_child`: Small child chunks (`max_chars=180`) for dense/keyword retrieval linked via `parent_chunk_id` to larger parent chunks (`max_chars=600`) for context expansion.
4. `structure_aware`: Structure-aware chunking for tables/rows that prepends entity schema headers (`[Entity | Table | PK]`) to every row/attribute segment.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from alba_one.kb.extractors import KnowledgeDocumentRecord

SUPPORTED_CHUNKING_STRATEGIES: tuple[str, ...] = (
    "recursive_ja",
    "semantic",
    "parent_child",
    "structure_aware",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])\s*|\n+")


@dataclass(frozen=True)
class KBChunkCandidate:
    """A single chunk produced by a chunking strategy prior to indexing."""

    chunk_id: str
    document_id: str
    tenant_id: str
    entity_type: str
    chunk_index: int
    strategy: str
    text: str
    source_table: str
    source_pk: str
    entity_ids: list[str]
    acl_tags: list[str]
    valid_from: str
    valid_to: str | None
    lang: str
    parent_chunk_id: str | None = None
    is_parent: bool = False
    is_synthetic: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


def _deterministic_chunk_id(
    tenant_id: str,
    source_table: str,
    source_pk: str,
    lang: str,
    strategy: str,
    chunk_index: int,
    role_prefix: str = "chk",
) -> str:
    seed = f"{tenant_id}|{source_table}|{source_pk}|{lang}|{strategy}|{role_prefix}|{chunk_index}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{role_prefix}_{strategy}_{lang}_{digest}"


def split_japanese_sentences(text: str) -> list[str]:
    """Split Japanese or English text on sentence boundaries (`。`, `！`, `？`, `.`, `!`, `?`, `\n`)."""
    if not text or not text.strip():
        return []
    # Also split on English period followed by space
    intermediate = re.sub(r"\.\s+", "。\n", text.strip())
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(intermediate) if p and p.strip()]
    return parts if parts else [text.strip()]


def _char_ngram_cosine(a: str, b: str, n: int = 2) -> float:
    """Compute character n-gram cosine similarity in [0, 1] between two sentences."""
    if not a or not b:
        return 0.0
    ca = Counter(a[i : i + n] for i in range(max(1, len(a) - n + 1)))
    cb = Counter(b[i : i + n] for i in range(max(1, len(b) - n + 1)))
    dot = sum(ca[k] * cb[k] for k in set(ca) & set(cb))
    norm_a = math.sqrt(sum(v * v for v in ca.values()))
    norm_b = math.sqrt(sum(v * v for v in cb.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def chunk_recursive_ja(
    doc: KnowledgeDocumentRecord,
    redacted_text: str,
    *,
    max_chars: int = 220,
    overlap_sentences: int = 1,
) -> list[KBChunkCandidate]:
    """Strategy (a): Recursive sentence-boundary chunker respecting `。！？` and newlines."""
    sentences = split_japanese_sentences(redacted_text)
    segments: list[str] = []
    current: list[str] = []
    current_len = 0

    for sent in sentences:
        if current and current_len + len(sent) > max_chars:
            segments.append(" ".join(current))
            current = current[-overlap_sentences:] if overlap_sentences > 0 else []
            current_len = sum(len(s) for s in current)
        current.append(sent)
        current_len += len(sent)

    if current:
        segments.append(" ".join(current))

    return [
        KBChunkCandidate(
            chunk_id=_deterministic_chunk_id(
                doc.tenant_id, doc.source_table, doc.source_pk, doc.lang, "recursive_ja", idx
            ),
            document_id=doc.doc_id,
            tenant_id=doc.tenant_id,
            entity_type=doc.entity_type,
            chunk_index=idx,
            strategy="recursive_ja",
            text=seg,
            source_table=doc.source_table,
            source_pk=doc.source_pk,
            entity_ids=list(doc.entity_ids),
            acl_tags=list(doc.acl_tags),
            valid_from=doc.valid_from,
            valid_to=doc.valid_to,
            lang=doc.lang,
            is_synthetic=doc.is_synthetic,
        )
        for idx, seg in enumerate(segments)
    ]


def chunk_semantic(
    doc: KnowledgeDocumentRecord,
    redacted_text: str,
    *,
    similarity_threshold: float = 0.12,
    max_chars: int = 260,
) -> list[KBChunkCandidate]:
    """Strategy (b): Semantic chunker splitting when adjacent sentence similarity drops below threshold."""
    sentences = split_japanese_sentences(redacted_text)
    if not sentences:
        return []

    segments: list[str] = []
    buf: list[str] = [sentences[0]]

    for prev, curr in zip(sentences, sentences[1:]):
        sim = _char_ngram_cosine(prev, curr)
        buf_len = sum(len(s) for s in buf)
        if sim < similarity_threshold or (buf_len + len(curr) > max_chars):
            segments.append(" ".join(buf))
            buf = [curr]
        else:
            buf.append(curr)

    if buf:
        segments.append(" ".join(buf))

    return [
        KBChunkCandidate(
            chunk_id=_deterministic_chunk_id(
                doc.tenant_id, doc.source_table, doc.source_pk, doc.lang, "semantic", idx
            ),
            document_id=doc.doc_id,
            tenant_id=doc.tenant_id,
            entity_type=doc.entity_type,
            chunk_index=idx,
            strategy="semantic",
            text=seg,
            source_table=doc.source_table,
            source_pk=doc.source_pk,
            entity_ids=list(doc.entity_ids),
            acl_tags=list(doc.acl_tags),
            valid_from=doc.valid_from,
            valid_to=doc.valid_to,
            lang=doc.lang,
            is_synthetic=doc.is_synthetic,
        )
        for idx, seg in enumerate(segments)
    ]


def chunk_parent_child(
    doc: KnowledgeDocumentRecord,
    redacted_text: str,
    *,
    parent_max_chars: int = 500,
    child_max_chars: int = 160,
) -> list[KBChunkCandidate]:
    """Strategy (c): Parent-child chunking (small child chunks for retrieval, parent for context)."""
    parent_id = _deterministic_chunk_id(
        doc.tenant_id, doc.source_table, doc.source_pk, doc.lang, "parent_child", 0, role_prefix="par"
    )
    parent_text = f"{doc.title} — {redacted_text}"[:parent_max_chars]

    sentences = split_japanese_sentences(redacted_text)
    child_segments: list[str] = []
    buf: list[str] = []
    for sent in sentences:
        if buf and sum(len(s) for s in buf) + len(sent) > child_max_chars:
            child_segments.append(" ".join(buf))
            buf = [sent]
        else:
            buf.append(sent)
    if buf:
        child_segments.append(" ".join(buf))

    results: list[KBChunkCandidate] = []
    for idx, seg in enumerate(child_segments):
        results.append(
            KBChunkCandidate(
                chunk_id=_deterministic_chunk_id(
                    doc.tenant_id, doc.source_table, doc.source_pk, doc.lang, "parent_child", idx
                ),
                document_id=doc.doc_id,
                tenant_id=doc.tenant_id,
                entity_type=doc.entity_type,
                chunk_index=idx,
                strategy="parent_child",
                text=f"[{doc.title}] {seg}",
                source_table=doc.source_table,
                source_pk=doc.source_pk,
                entity_ids=list(doc.entity_ids),
                acl_tags=list(doc.acl_tags),
                valid_from=doc.valid_from,
                valid_to=doc.valid_to,
                lang=doc.lang,
                parent_chunk_id=parent_id,
                is_parent=False,
                is_synthetic=doc.is_synthetic,
                metadata={"parent_text": parent_text},
            )
        )
    return results


def chunk_structure_aware(
    doc: KnowledgeDocumentRecord,
    redacted_text: str,
) -> list[KBChunkCandidate]:
    """Strategy (d): Structure-aware chunker preserving table/row schema headers and attributes."""
    header = (
        f"[Entity={doc.entity_type} | Table={doc.source_table} | PK={doc.source_pk} | "
        f"IDs={','.join(doc.entity_ids)}]"
    )
    kv_pairs = [
        f"{k}={v}"
        for k, v in sorted(doc.structured_metadata.items())
        if k not in ("name_ja", "name_en")
    ]
    structured_block = f"{header}\n{doc.title}\n{redacted_text}\nAttributes: {'; '.join(kv_pairs)}"
    return [
        KBChunkCandidate(
            chunk_id=_deterministic_chunk_id(
                doc.tenant_id, doc.source_table, doc.source_pk, doc.lang, "structure_aware", 0
            ),
            document_id=doc.doc_id,
            tenant_id=doc.tenant_id,
            entity_type=doc.entity_type,
            chunk_index=0,
            strategy="structure_aware",
            text=structured_block,
            source_table=doc.source_table,
            source_pk=doc.source_pk,
            entity_ids=list(doc.entity_ids),
            acl_tags=list(doc.acl_tags),
            valid_from=doc.valid_from,
            valid_to=doc.valid_to,
            lang=doc.lang,
            is_synthetic=doc.is_synthetic,
        )
    ]


def chunk_document(
    doc: KnowledgeDocumentRecord,
    redacted_text: str,
    strategy: str = "parent_child",
) -> list[KBChunkCandidate]:
    """Dispatch document chunking to one of the 4 supported strategies."""
    if strategy == "recursive_ja":
        return chunk_recursive_ja(doc, redacted_text)
    if strategy == "semantic":
        return chunk_semantic(doc, redacted_text)
    if strategy == "parent_child":
        return chunk_parent_child(doc, redacted_text)
    if strategy == "structure_aware":
        return chunk_structure_aware(doc, redacted_text)
    raise ValueError(
        f"Unknown chunking strategy '{strategy}'. Must be one of {SUPPORTED_CHUNKING_STRATEGIES}."
    )
