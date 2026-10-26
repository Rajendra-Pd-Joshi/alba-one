"""Public exports for `alba_one.kb` (Phase 2: Knowledge Base & Ingestion)."""

from alba_one.kb.chunkers import (
    SUPPORTED_CHUNKING_STRATEGIES,
    KBChunkCandidate,
    chunk_document,
    chunk_parent_child,
    chunk_recursive_ja,
    chunk_semantic,
    chunk_structure_aware,
    split_japanese_sentences,
)
from alba_one.kb.embedder import DeterministicHashEmbedder, EmbeddingProvider
from alba_one.kb.extractors import (
    ALLOWED_EXTRACTION_VIEWS,
    KnowledgeDocumentRecord,
    build_readonly_view_sql,
    extract_documents_from_seed_snapshot,
)
from alba_one.kb.fts import build_tokenized_tsvector_string, score_fts_match, tokenize_for_fts
from alba_one.kb.indexer import (
    ALLOWED_PINECONE_METADATA_KEYS,
    FORBIDDEN_PINECONE_TEXT_KEYS,
    IndexingReport,
    InMemoryOnPremStore,
    InMemoryPineconeStore,
    KnowledgeBaseIndexer,
    assert_pinecone_metadata_safe,
    build_default_demo_kb,
    build_pinecone_metadata,
    resolve_tenant_alias,
)
from alba_one.kb.ontology_logic import (
    REQUIRED_ENTITY_TYPES,
    EntitySpec,
    OntologyCatalog,
    RelationSpec,
    load_ontology_catalog,
)
from alba_one.kb.pii import PIIRedactionResult, PIIRedactor

__all__ = [
    "ALLOWED_EXTRACTION_VIEWS",
    "ALLOWED_PINECONE_METADATA_KEYS",
    "FORBIDDEN_PINECONE_TEXT_KEYS",
    "REQUIRED_ENTITY_TYPES",
    "SUPPORTED_CHUNKING_STRATEGIES",
    "DeterministicHashEmbedder",
    "EmbeddingProvider",
    "EntitySpec",
    "InMemoryOnPremStore",
    "InMemoryPineconeStore",
    "IndexingReport",
    "KBChunkCandidate",
    "KnowledgeBaseIndexer",
    "KnowledgeDocumentRecord",
    "OntologyCatalog",
    "PIIRedactionResult",
    "PIIRedactor",
    "RelationSpec",
    "assert_pinecone_metadata_safe",
    "build_default_demo_kb",
    "build_pinecone_metadata",
    "build_readonly_view_sql",
    "build_tokenized_tsvector_string",
    "chunk_document",
    "chunk_parent_child",
    "chunk_recursive_ja",
    "chunk_semantic",
    "chunk_structure_aware",
    "extract_documents_from_seed_snapshot",
    "load_ontology_catalog",
    "resolve_tenant_alias",
    "score_fts_match",
    "split_japanese_sentences",
    "tokenize_for_fts",
]
