"""Knowledge base indexer (`kb/indexer.py`) and CLI entrypoint.

Enforces Phase 2 Requirement 6:
1. Full text stays in on-prem Postgres (`kb_documents` & `kb_chunks`).
2. PII is redacted BEFORE embedding.
3. Pinecone stores ONLY `chunk_id, tenant_id, acl_tags, entity_type, lang, valid_from, valid_to`
   as metadata inside `namespace=tenant_id` (NEVER chunk text).
4. Supports idempotent full re-index, incremental updates, deletion propagation, and `--dry-run`.

CLI:
    uv run python -m alba_one.kb.indexer --tenant demo --full|--incremental [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from alba_one.kb.chunkers import KBChunkCandidate, chunk_document
from alba_one.kb.embedder import DeterministicHashEmbedder, EmbeddingProvider
from alba_one.kb.extractors import KnowledgeDocumentRecord, extract_documents_from_seed_snapshot
from alba_one.kb.fts import build_tokenized_tsvector_string
from alba_one.kb.ontology_logic import OntologyCatalog, load_ontology_catalog
from alba_one.kb.pii import PIIRedactor

ALLOWED_PINECONE_METADATA_KEYS: frozenset[str] = frozenset(
    {"chunk_id", "tenant_id", "acl_tags", "entity_type", "lang", "valid_from", "valid_to"}
)
FORBIDDEN_PINECONE_TEXT_KEYS: frozenset[str] = frozenset(
    {"text", "tokenized_text", "content", "body", "quote", "quote_span", "parent_text", "title"}
)


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the `alba-one/` repository root containing `config/ontology_demo.yaml`."""
    cur = (start or Path(__file__)).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "config" / "ontology_demo.yaml").exists():
            return candidate
    return Path.cwd()


def resolve_tenant_alias(tenant_arg: str) -> str:
    """Expand friendly CLI alias `'demo'` to `'tenant_alba_demo'`."""
    cleaned = tenant_arg.strip()
    return "tenant_alba_demo" if cleaned == "demo" else cleaned


def assert_pinecone_metadata_safe(metadata: dict[str, Any]) -> None:
    """Raise ValueError if any forbidden text key or unapproved key is in Pinecone metadata."""
    keys = set(metadata.keys())
    forbidden = keys & FORBIDDEN_PINECONE_TEXT_KEYS
    if forbidden:
        raise ValueError(f"Chunk text key(s) {sorted(forbidden)} forbidden in Pinecone metadata.")
    unexpected = keys - ALLOWED_PINECONE_METADATA_KEYS
    if unexpected:
        raise ValueError(f"Unapproved Pinecone metadata key(s): {sorted(unexpected)}.")


def build_pinecone_metadata(chunk: KBChunkCandidate) -> dict[str, Any]:
    """Construct the strictly allowlisted Pinecone vector metadata (no chunk text!)."""
    meta: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "tenant_id": chunk.tenant_id,
        "acl_tags": list(chunk.acl_tags),
        "entity_type": chunk.entity_type,
        "lang": chunk.lang,
        "valid_from": chunk.valid_from,
        "valid_to": chunk.valid_to or "",
    }
    assert_pinecone_metadata_safe(meta)
    return meta


class VectorIndexStore(Protocol):
    """Protocol for Pinecone index operations, scoped by `namespace=tenant_id`."""

    def upsert_vectors(
        self, *, namespace: str, vectors: list[tuple[str, list[float], dict[str, Any]]]
    ) -> int: ...
    def delete_vectors(self, *, namespace: str, ids: list[str]) -> int: ...


class InMemoryPineconeStore:
    """# STUB: In-memory Pinecone index double enforcing strict metadata rules per tenant namespace."""

    def __init__(self) -> None:
        self.namespaces: dict[str, dict[str, tuple[list[float], dict[str, Any]]]] = {}

    def upsert_vectors(
        self, *, namespace: str, vectors: list[tuple[str, list[float], dict[str, Any]]]
    ) -> int:
        if not namespace.strip():
            raise ValueError("Pinecone namespace (tenant_id) is required.")
        bucket = self.namespaces.setdefault(namespace, {})
        for vec_id, values, meta in vectors:
            assert_pinecone_metadata_safe(meta)
            if meta.get("tenant_id") != namespace:
                raise PermissionError("Vector tenant_id must match Pinecone namespace.")
            bucket[vec_id] = (values, dict(meta))
        return len(vectors)

    def delete_vectors(self, *, namespace: str, ids: list[str]) -> int:
        bucket = self.namespaces.get(namespace, {})
        removed = sum(1 for vid in ids if bucket.pop(vid, None) is not None)
        return removed


@dataclass
class InMemoryOnPremStore:
    """# STUB: On-prem PostgreSQL store double holding `kb_documents` and `kb_chunks` (full text)."""

    documents: dict[str, KnowledgeDocumentRecord] = field(default_factory=dict)
    doc_hashes: dict[str, str] = field(default_factory=dict)
    chunks: dict[str, KBChunkCandidate] = field(default_factory=dict)
    tokenized_by_chunk: dict[str, str] = field(default_factory=dict)
    redacted_by_chunk: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexingReport:
    """Summary returned by an indexing run."""

    tenant_id: str
    mode: str
    strategy: str
    dry_run: bool
    documents_extracted: int
    documents_indexed: int
    documents_skipped_unchanged: int
    documents_deleted: int
    chunks_upserted: int
    chunks_deleted: int
    pii_redactions_total: int
    chunks_by_entity_type: dict[str, int]


class KnowledgeBaseIndexer:
    """Idempotent full and incremental KB indexer keeping full text on-prem and vectors in Pinecone."""

    def __init__(
        self,
        *,
        onprem_store: InMemoryOnPremStore,
        vector_store: VectorIndexStore,
        embedder: EmbeddingProvider | None = None,
        redactor: PIIRedactor | None = None,
        chunking_strategy: str = "parent_child",
    ) -> None:
        self.onprem = onprem_store
        self.vectors = vector_store
        self.embedder = embedder or DeterministicHashEmbedder(dimensions=1536)
        self.redactor = redactor or PIIRedactor()
        self.strategy = chunking_strategy

    def _delete_doc_chunks(self, tenant_id: str, doc_id: str, dry_run: bool) -> int:
        stale_cids = [
            cid
            for cid, c in self.onprem.chunks.items()
            if c.document_id == doc_id and c.tenant_id == tenant_id
        ]
        if not dry_run and stale_cids:
            self.vectors.delete_vectors(namespace=tenant_id, ids=stale_cids)
            for cid in stale_cids:
                self.onprem.chunks.pop(cid, None)
                self.onprem.tokenized_by_chunk.pop(cid, None)
                self.onprem.redacted_by_chunk.pop(cid, None)
        return len(stale_cids)

    def run(
        self,
        *,
        tenant_id: str,
        documents: list[KnowledgeDocumentRecord],
        mode: str = "full",
        dry_run: bool = False,
    ) -> IndexingReport:
        """Index `documents` for `tenant_id` idempotently with deletion propagation."""
        resolved = resolve_tenant_alias(tenant_id)
        for doc in documents:
            if doc.tenant_id != resolved:
                raise PermissionError(f"Cross-tenant document '{doc.doc_id}' rejected.")

        incoming_ids = {d.doc_id for d in documents}
        existing_ids = {
            did for did, d in self.onprem.documents.items() if d.tenant_id == resolved
        }

        docs_deleted = 0
        chunks_deleted = 0
        if mode == "full":
            for stale_did in sorted(existing_ids - incoming_ids):
                docs_deleted += 1
                chunks_deleted += self._delete_doc_chunks(resolved, stale_did, dry_run)
                if not dry_run:
                    self.onprem.documents.pop(stale_did, None)
                    self.onprem.doc_hashes.pop(stale_did, None)

        docs_indexed = docs_skipped = chunks_upserted = pii_total = 0
        for doc in documents:
            new_hash = doc.content_hash
            if self.onprem.doc_hashes.get(doc.doc_id) == new_hash:
                docs_skipped += 1
                continue

            docs_indexed += 1
            pii_res = self.redactor.redact(doc.text)
            pii_total += pii_res.total_redactions
            doc_chunks = chunk_document(doc, pii_res.redacted_text, strategy=self.strategy)
            embeddings = self.embedder.embed_documents([c.text for c in doc_chunks])

            chunks_deleted += self._delete_doc_chunks(resolved, doc.doc_id, dry_run)
            batch = [(c.chunk_id, v, build_pinecone_metadata(c)) for c, v in zip(doc_chunks, embeddings)]
            chunks_upserted += len(batch)
            if not dry_run:
                for chk in doc_chunks:
                    self.onprem.chunks[chk.chunk_id] = chk
                    self.onprem.tokenized_by_chunk[chk.chunk_id] = build_tokenized_tsvector_string(chk.text)
                    self.onprem.redacted_by_chunk[chk.chunk_id] = chk.text
                self.vectors.upsert_vectors(namespace=resolved, vectors=batch)
                self.onprem.documents[doc.doc_id] = doc
                self.onprem.doc_hashes[doc.doc_id] = new_hash

        counts: dict[str, int] = {}
        for chk in self.onprem.chunks.values():
            if chk.tenant_id == resolved:
                counts[chk.entity_type] = counts.get(chk.entity_type, 0) + 1

        return IndexingReport(
            tenant_id=resolved,
            mode=mode,
            strategy=self.strategy,
            dry_run=dry_run,
            documents_extracted=len(documents),
            documents_indexed=docs_indexed,
            documents_skipped_unchanged=docs_skipped,
            documents_deleted=docs_deleted,
            chunks_upserted=chunks_upserted,
            chunks_deleted=chunks_deleted,
            pii_redactions_total=pii_total,
            chunks_by_entity_type=counts,
        )


def build_default_demo_kb(
    *, repo_root: str | Path | None = None, strategy: str = "parent_child"
) -> tuple[KnowledgeBaseIndexer, OntologyCatalog, IndexingReport]:
    """Bootstrap and index the synthetic demo company into an in-memory on-prem + vector store."""
    root = Path(repo_root) if repo_root else find_repo_root()
    ontology = load_ontology_catalog(root / "config" / "ontology_demo.yaml")
    docs = extract_documents_from_seed_snapshot(root / "infra" / "seed" / "synthetic_demo_data.json", ontology)
    indexer = KnowledgeBaseIndexer(
        onprem_store=InMemoryOnPremStore(),
        vector_store=InMemoryPineconeStore(),
        chunking_strategy=strategy,
    )
    report = indexer.run(tenant_id=ontology.tenant_id, documents=docs, mode="full", dry_run=False)
    return indexer, ontology, report


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: `uv run python -m alba_one.kb.indexer --tenant demo --full|--incremental`."""
    parser = argparse.ArgumentParser(description="ALBA ONE Knowledge Base Indexer")
    parser.add_argument("--tenant", required=True, help="Tenant ID (or 'demo' for tenant_alba_demo)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true")
    group.add_argument("--incremental", action="store_true")
    parser.add_argument("--since", default=None)
    parser.add_argument("--strategy", default="parent_child")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = find_repo_root()
    tenant_id = resolve_tenant_alias(args.tenant)
    ontology = load_ontology_catalog(root / "config" / "ontology_demo.yaml", expected_tenant_id=tenant_id)
    docs = extract_documents_from_seed_snapshot(
        root / "infra" / "seed" / "synthetic_demo_data.json",
        ontology,
        incremental_since=args.since if args.incremental else None,
    )
    indexer = KnowledgeBaseIndexer(
        onprem_store=InMemoryOnPremStore(),
        vector_store=InMemoryPineconeStore(),
        chunking_strategy=args.strategy,
    )
    report = indexer.run(
        tenant_id=tenant_id,
        documents=docs,
        mode="full" if args.full else "incremental",
        dry_run=args.dry_run,
    )
    print(json.dumps(report.__dict__, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
