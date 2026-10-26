"""Unit tests for Phase 2 Indexer (`kb/indexer.py`) and Knowledge-Base MCP Service (`mcp_servers/knowledge_base`)."""

from __future__ import annotations

import importlib.util as _ilu
import pathlib as _pl
import unittest

_spec = _ilu.spec_from_file_location("_bootstrap", _pl.Path(__file__).with_name("_bootstrap.py"))
assert _spec and _spec.loader
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from alba_one.kb.indexer import (  # noqa: E402
    ALLOWED_PINECONE_METADATA_KEYS,
    assert_pinecone_metadata_safe,
    build_default_demo_kb,
)
from alba_one.mcp_servers.knowledge_base.service import KnowledgeBaseService  # noqa: E402

REPO_ROOT = _pl.Path(__file__).resolve().parents[4]


class TestIndexerAndKBMCP(unittest.TestCase):
    """Verify no chunk text in Pinecone, idempotent re-indexing, deletion propagation, and MCP ACLs."""

    def test_no_chunk_text_exists_in_pinecone_and_reindex_is_idempotent(self) -> None:
        indexer, ontology, report1 = build_default_demo_kb(repo_root=REPO_ROOT)

        self.assertEqual(report1.tenant_id, "tenant_alba_demo")
        self.assertGreater(report1.documents_indexed, 0)
        self.assertEqual(report1.documents_skipped_unchanged, 0)
        self.assertGreater(report1.chunks_upserted, 0)
        self.assertGreater(report1.pii_redactions_total, 0)

        # Verify every vector stored in Pinecone has ONLY the 7 allowed metadata keys and NO chunk text
        vec_store = indexer.vectors
        ns_bucket = getattr(vec_store, "namespaces")["tenant_alba_demo"]
        self.assertEqual(len(ns_bucket), report1.chunks_upserted)
        for vec_id, (vec_vals, meta) in ns_bucket.items():
            self.assertEqual(len(vec_vals), 1536)
            self.assertEqual(set(meta.keys()), ALLOWED_PINECONE_METADATA_KEYS)
            self.assertNotIn("text", meta)
            self.assertNotIn("content", meta)
            # And verify PII was scrubbed from the on-prem indexed chunk text
            onprem_chunk = indexer.onprem.chunks[vec_id]
            self.assertNotIn("渡辺 剛", onprem_chunk.text)
            self.assertNotIn("090-1234-5678", onprem_chunk.text)

        # Second run with identical documents must skip 100% as unchanged (idempotent)
        docs = list(indexer.onprem.documents.values())
        report2 = indexer.run(tenant_id="tenant_alba_demo", documents=docs, mode="full")
        self.assertEqual(report2.documents_indexed, 0)
        self.assertEqual(report2.documents_skipped_unchanged, len(docs))
        self.assertEqual(report2.chunks_upserted, 0)

        # Deletion propagation: removing 2 documents deletes their chunks from both on-prem and Pinecone
        subset_docs = docs[:-2]
        report3 = indexer.run(tenant_id="tenant_alba_demo", documents=subset_docs, mode="full")
        self.assertEqual(report3.documents_deleted, 2)
        self.assertGreaterEqual(report3.chunks_deleted, 2)

    def test_pinecone_metadata_guard_rejects_text_fields(self) -> None:
        with self.assertRaises(ValueError):
            assert_pinecone_metadata_safe(
                {
                    "chunk_id": "c1",
                    "tenant_id": "t1",
                    "acl_tags": ["role:viewer"],
                    "entity_type": "vessel",
                    "lang": "ja",
                    "valid_from": "2026-10-24",
                    "valid_to": "",
                    "text": "Forbidden chunk text!",
                }
            )

    def test_kb_mcp_service_resolves_text_from_onprem_and_enforces_acl(self) -> None:
        svc = KnowledgeBaseService.create_demo_default()

        # Query for vessel berth in Japanese
        hits = svc.kb_search(
            tenant_id="tenant_alba_demo",
            caller_role="viewer",
            query="アルバ・オーロラ号 東京港大井第3バース TYO-OI-B3",
            lang="ja",
            top_k=3,
        )
        self.assertGreaterEqual(len(hits), 1)
        top_hit = hits[0]
        self.assertIn("TYO-OI-B3", top_hit["text"])

        # Fetch chunk directly by chunk_id
        chunk_detail = svc.kb_get_chunk(
            tenant_id="tenant_alba_demo",
            caller_role="viewer",
            chunk_id=top_hit["chunk_id"],
        )
        self.assertEqual(chunk_detail["chunk_id"], top_hit["chunk_id"])

        # ACL check: 'viewer' role cannot access 'staff' entity or 'staff' chunks
        with self.assertRaises(PermissionError):
            svc.kb_get_entity(
                tenant_id="tenant_alba_demo",
                caller_role="viewer",
                entity_type="staff",
            )

        staff_Chunks = [
            c for c in svc.indexer.onprem.chunks.values() if c.entity_type == "staff"
        ]
        self.assertGreaterEqual(len(staff_Chunks), 1)
        with self.assertRaises(PermissionError):
            svc.kb_get_chunk(
                tenant_id="tenant_alba_demo",
                caller_role="viewer",
                chunk_id=staff_Chunks[0].chunk_id,
            )

        # 'analyst' role CAN access 'staff' entity and chunks
        staff_entity = svc.kb_get_entity(
            tenant_id="tenant_alba_demo",
            caller_role="analyst",
            entity_type="staff",
        )
        self.assertEqual(staff_entity["entity_type"], "staff")
        self.assertGreater(staff_entity["chunk_count"], 0)


if __name__ == "__main__":
    unittest.main()
