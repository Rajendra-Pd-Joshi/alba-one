"""FastMCP server for the ALBA ONE Knowledge Base (`mcp_servers/knowledge_base/server.py`).

Principle 1: Every capability the planner uses is an MCP server consumed through
`langchain-mcp-adapters`.
Exposes 4 read-only tools with bilingual descriptions and server-side ACL enforcement:
- `kb_search`
- `kb_get_chunk`
- `kb_get_entity`
- `kb_list_entities`
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime
from alba_one.mcp_servers.knowledge_base.schemas import (
    KBEntitySummary,
    KBGetChunkInput,
    KBGetChunkOutput,
    KBGetEntityInput,
    KBListEntitiesInput,
    KBListEntitiesOutput,
    KBSearchHit,
    KBSearchInput,
    KBSearchOutput,
)
from alba_one.mcp_servers.knowledge_base.service import KnowledgeBaseService

mcp = FastMCP("alba-knowledge-base")
runtime = get_server_runtime("knowledge_base")
_service: KnowledgeBaseService | None = None


def get_kb_service() -> KnowledgeBaseService:
    """Return or initialize the singleton `KnowledgeBaseService`."""
    global _service
    if _service is None:
        _service = KnowledgeBaseService.create_demo_default()
    return _service


@mcp.tool(
    name="kb_search",
    description=(
        "Search the tenant-isolated knowledge base with ACL filtering and resolve full chunk "
        "text from on-premise PostgreSQL. / テナント分離およびACL権限フィルタを適用してナレッジベースを検索します。"
    ),
)
def kb_search(payload: KBSearchInput) -> KBSearchOutput:
    """Execute hybrid vector + FTS search and return ACL-authorized chunks."""
    svc = get_kb_service()
    raw_hits = svc.kb_search(
        tenant_id=payload.tenant_id,
        caller_role=payload.caller_role,
        query=payload.query,
        lang=payload.lang,
        entity_type=payload.entity_type,
        top_k=payload.top_k,
    )
    return KBSearchOutput(
        tenant_id=payload.tenant_id,
        hits=[KBSearchHit(**h) for h in raw_hits],
    )


@mcp.tool(
    name="kb_get_chunk",
    description=(
        "Retrieve a single knowledge base chunk by chunk_id from on-prem PostgreSQL with ACL check. / "
        "chunk_idを指定してオンプレミスPostgreSQLからチャンク本文を取得します（ACL検証付）。"
    ),
)
def kb_get_chunk(payload: KBGetChunkInput) -> KBGetChunkOutput:
    """Return full chunk details if authorized for `tenant_id` and `caller_role`."""
    svc = get_kb_service()
    data = svc.kb_get_chunk(
        tenant_id=payload.tenant_id,
        caller_role=payload.caller_role,
        chunk_id=payload.chunk_id,
    )
    return KBGetChunkOutput(**data)


@mcp.tool(
    name="kb_get_entity",
    description=(
        "Inspect business ontology metadata and chunk count for an entity type. / "
        "指定した業務エンティティ種別のオントロジー定義・意思決定フィールド・チャンク数を取得します。"
    ),
)
def kb_get_entity(payload: KBGetEntityInput) -> KBEntitySummary:
    """Return `KBEntitySummary` if caller role is permitted by the entity's ACL tags."""
    svc = get_kb_service()
    data = svc.kb_get_entity(
        tenant_id=payload.tenant_id,
        caller_role=payload.caller_role,
        entity_type=payload.entity_type,
    )
    return KBEntitySummary(**data)


@mcp.tool(
    name="kb_list_entities",
    description=(
        "List all business entities in the tenant ontology accessible to the caller's role. / "
        "呼び出し元のロールがアクセス可能な業務エンティティ一覧を取得します。"
    ),
)
def kb_list_entities(payload: KBListEntitiesInput) -> KBListEntitiesOutput:
    """Return all ACL-visible entities for `tenant_id`."""
    svc = get_kb_service()
    items = svc.kb_list_entities(
        tenant_id=payload.tenant_id,
        caller_role=payload.caller_role,
    )
    return KBListEntitiesOutput(
        tenant_id=payload.tenant_id,
        entities=[KBEntitySummary(**item) for item in items],
    )


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8101))
