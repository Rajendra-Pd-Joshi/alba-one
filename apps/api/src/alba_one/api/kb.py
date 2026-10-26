"""FastAPI router for Knowledge Base endpoints (`/api/kb/status`, `/api/kb/entities`, `/api/kb/reindex`)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from alba_one.core.tenancy import get_tenant_context, get_user_context, require_role
from alba_one.kb.extractors import extract_documents_from_seed_snapshot
from alba_one.kb.indexer import find_repo_root
from alba_one.mcp_servers.knowledge_base.server import get_kb_service
from alba_one.schemas.common import TenantContext, UserContext, UserRole

router = APIRouter(tags=["kb"])


@router.get("/api/kb/status")
@router.get("/api/v1/kb/status")
async def get_kb_status(
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return current knowledge base indexing status and chunk counts per entity type."""
    svc = get_kb_service()
    chunks_by_entity: dict[str, int] = {}
    total_chunks = 0
    for chk in svc.indexer.onprem.chunks.values():
        if chk.tenant_id == tenant.tenant_id:
            total_chunks += 1
            chunks_by_entity[chk.entity_type] = chunks_by_entity.get(chk.entity_type, 0) + 1

    total_docs = sum(
        1 for d in svc.indexer.onprem.documents.values() if d.tenant_id == tenant.tenant_id
    )
    return {
        "tenant_id": tenant.tenant_id,
        "chunking_strategy": svc.indexer.strategy,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "chunks_by_entity_type": chunks_by_entity,
        "pinecone_stores_chunk_text": False,
    }


@router.get("/api/kb/entities")
@router.get("/api/v1/kb/entities")
async def list_kb_entities(
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return ontology entities filtered by the authenticated user's role ACL tags."""
    svc = get_kb_service()
    entities = svc.kb_list_entities(
        tenant_id=tenant.tenant_id,
        caller_role=user.role.value,
    )
    return {
        "tenant_id": tenant.tenant_id,
        "role": user.role.value,
        "entities": entities,
    }


@router.post("/api/kb/reindex")
@router.post("/api/v1/kb/reindex")
async def trigger_kb_reindex(
    mode: str = Query(default="full", pattern="^(full|incremental)$"),
    dry_run: bool = Query(default=False),
    tenant: TenantContext = Depends(get_tenant_context),
    admin_user: UserContext = Depends(require_role(UserRole.ADMIN)),
) -> dict[str, Any]:
    """Trigger a full or incremental KB re-index for the current tenant (admin role required)."""
    svc = get_kb_service()
    root = find_repo_root()
    docs = extract_documents_from_seed_snapshot(
        root / "infra" / "seed" / "synthetic_demo_data.json",
        svc.ontology,
    )
    report = svc.indexer.run(
        tenant_id=tenant.tenant_id,
        documents=docs,
        mode=mode,
        dry_run=dry_run,
    )
    return {
        "triggered_by": admin_user.user_id,
        "report": asdict(report),
    }
