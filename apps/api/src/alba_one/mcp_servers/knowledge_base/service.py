"""Pure Knowledge Base service layer backing both the FastMCP server and `/api/kb/*` endpoints.

Enforces server-side multi-tenant isolation (`tenant_id`) and ACL tag filtering
(`role:{caller_role}`) on all 4 KB operations:
- `kb_search`
- `kb_get_chunk`
- `kb_get_entity`
- `kb_list_entities`
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from alba_one.kb.fts import score_fts_match
from alba_one.kb.indexer import KnowledgeBaseIndexer, build_default_demo_kb
from alba_one.kb.ontology_logic import OntologyCatalog


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, min(1.0, (dot / (na * nb) + 1.0) / 2.0))


def _caller_acl_tags(caller_role: str, extra_acl_tags: list[str] | None = None) -> set[str]:
    tags = {f"role:{caller_role.strip().lower()}"}
    if extra_acl_tags:
        tags.update(t.strip() for t in extra_acl_tags if t.strip())
    return tags


class KnowledgeBaseService:
    """Server-side ACL-enforced KB query service resolving chunk text from on-prem storage."""

    def __init__(self, indexer: KnowledgeBaseIndexer, ontology: OntologyCatalog) -> None:
        self.indexer = indexer
        self.ontology = ontology
        self._last_report = None

    @classmethod
    def create_demo_default(cls) -> KnowledgeBaseService:
        indexer, ontology, report = build_default_demo_kb()
        svc = cls(indexer=indexer, ontology=ontology)
        svc._last_report = report
        return svc

    def kb_search(
        self,
        *,
        tenant_id: str,
        caller_role: str,
        query: str,
        lang: str | None = None,
        entity_type: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search Pinecone vector metadata + on-prem FTS, enforce ACLs, and resolve chunk text from on-prem."""
        allowed_acl = _caller_acl_tags(caller_role)
        q_vec = self.indexer.embedder.embed_query(query)
        namespace_vectors = getattr(self.indexer.vectors, "namespaces", {}).get(tenant_id, {})

        scored: list[tuple[float, str]] = []
        for chunk_id, (vec, meta) in namespace_vectors.items():
            if meta.get("tenant_id") != tenant_id:
                continue
            if lang and meta.get("lang") != lang:
                continue
            if entity_type and meta.get("entity_type") != entity_type:
                continue
            chunk_acls = set(meta.get("acl_tags", []))
            if not (chunk_acls & allowed_acl):
                continue

            dense_score = _cosine_similarity(q_vec, vec)
            tok_str = self.indexer.onprem.tokenized_by_chunk.get(chunk_id, "")
            fts_score = score_fts_match(query, tok_str)
            hybrid_score = round(0.4 * dense_score + 0.6 * fts_score, 4)
            scored.append((hybrid_score, chunk_id))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, chunk_id in scored[: max(1, top_k)]:
            # Resolve chunk text strictly from on-prem store (never stored in Pinecone)
            chk = self.indexer.onprem.chunks.get(chunk_id)
            if chk is None or chk.tenant_id != tenant_id:
                continue
            results.append(
                {
                    "chunk_id": chk.chunk_id,
                    "tenant_id": chk.tenant_id,
                    "text": chk.text,
                    "score": score,
                    "source_table": chk.source_table,
                    "entity_type": chk.entity_type,
                    "entity_ids": list(chk.entity_ids),
                    "acl_tags": list(chk.acl_tags),
                    "lang": chk.lang,
                }
            )
        return results

    def kb_get_chunk(
        self,
        *,
        tenant_id: str,
        caller_role: str,
        chunk_id: str,
    ) -> dict[str, Any]:
        """Fetch a single chunk by ID from on-prem Postgres store with tenant and ACL checks."""
        chk = self.indexer.onprem.chunks.get(chunk_id)
        if chk is None or chk.tenant_id != tenant_id:
            raise KeyError(f"Chunk '{chunk_id}' not found for tenant '{tenant_id}'.")

        allowed_acl = _caller_acl_tags(caller_role)
        if not (set(chk.acl_tags) & allowed_acl):
            raise PermissionError(
                f"Role '{caller_role}' does not have ACL permission to read chunk '{chunk_id}'."
            )
        return {
            "chunk_id": chk.chunk_id,
            "document_id": chk.document_id,
            "tenant_id": chk.tenant_id,
            "text": chk.text,
            "source_table": chk.source_table,
            "entity_type": chk.entity_type,
            "entity_ids": list(chk.entity_ids),
            "acl_tags": list(chk.acl_tags),
            "valid_from": chk.valid_from,
            "valid_to": chk.valid_to,
            "lang": chk.lang,
            "parent_chunk_id": chk.parent_chunk_id,
        }

    def kb_list_entities(
        self,
        *,
        tenant_id: str,
        caller_role: str,
    ) -> list[dict[str, Any]]:
        """List business entities in the tenant's ontology filtered by the caller's ACL tags."""
        if tenant_id != self.ontology.tenant_id:
            raise PermissionError(f"Tenant mismatch: expected '{self.ontology.tenant_id}', got '{tenant_id}'.")
        allowed_acl = _caller_acl_tags(caller_role)
        specs = self.ontology.filter_entities_for_acl(allowed_acl)
        return [asdict(s) for s in specs]

    def kb_get_entity(
        self,
        *,
        tenant_id: str,
        caller_role: str,
        entity_type: str,
    ) -> dict[str, Any]:
        """Return ontology definition and active chunk count for a single business entity type."""
        if tenant_id != self.ontology.tenant_id:
            raise PermissionError(f"Tenant mismatch: expected '{self.ontology.tenant_id}', got '{tenant_id}'.")
        spec = self.ontology.entities.get(entity_type)
        if spec is None:
            raise KeyError(f"Entity type '{entity_type}' not found in ontology.")

        allowed_acl = _caller_acl_tags(caller_role)
        if not (set(spec.acl_tags) & allowed_acl):
            raise PermissionError(
                f"Role '{caller_role}' is not permitted to access entity '{entity_type}'."
            )
        chunk_count = sum(
            1
            for c in self.indexer.onprem.chunks.values()
            if c.tenant_id == tenant_id and c.entity_type == entity_type
        )
        payload = asdict(spec)
        payload["chunk_count"] = chunk_count
        return payload
