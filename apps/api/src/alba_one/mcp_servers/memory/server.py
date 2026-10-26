"""FastMCP server for ALBA ONE Long-Term Memory (`mcp_servers/memory/server.py`).

Per User Answer 2:
Exposes ONLY 4 tools:
1. `search_memories`
2. `list_my_memories`
3. `delete_memory` (user-initiated)
4. `propose_memory` (goes through `MemoryService` write policy; requires `approval_id` or `user_confirmed=True`).
No raw `add` tool is exposed to the planner.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime
from alba_one.mcp_servers.memory.schemas import (
    DeleteMemoryInput,
    ListMyMemoriesInput,
    MemoryRecordOutput,
    ProposeMemoryInput,
    SearchMemoriesInput,
)
from alba_one.memory.long_term import InMemoryLongTermAdapter, MemoryItem, MemoryService

mcp = FastMCP("alba-memory")
runtime = get_server_runtime("memory")
_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """Return or initialize the singleton `MemoryService`."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService(adapter=InMemoryLongTermAdapter())
    return _memory_service


def _to_output(item: MemoryItem) -> MemoryRecordOutput:
    return MemoryRecordOutput(
        memory_id=item.memory_id,
        tenant_id=item.tenant_id,
        user_id=item.user_id,
        team_id=item.team_id,
        memory_type=item.memory_type,
        topic_key=item.topic_key,
        content=item.content,
        lang=item.lang,
        approval_id=item.approval_id,
        user_confirmed=item.user_confirmed,
    )


@mcp.tool(
    name="search_memories",
    description=(
        "Search long-term memories scoped to (tenant_id, user_id, team_id). / "
        "テナント・ユーザー境界内で長期メモリを検索します。"
    ),
)
def search_memories(payload: SearchMemoriesInput) -> list[MemoryRecordOutput]:
    svc = get_memory_service()
    items = svc.search_memories(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        query=payload.query,
        team_id=payload.team_id,
        top_k=payload.top_k,
    )
    return [_to_output(m) for m in items]


@mcp.tool(
    name="list_my_memories",
    description=(
        "List all active long-term memories visible to the current user. / "
        "現在のユーザーが参照可能な有効な長期メモリ一覧を取得します。"
    ),
)
def list_my_memories(payload: ListMyMemoriesInput) -> list[MemoryRecordOutput]:
    svc = get_memory_service()
    items = svc.list_my_memories(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        team_id=payload.team_id,
    )
    return [_to_output(m) for m in items]


@mcp.tool(
    name="delete_memory",
    description=(
        "Delete a specific long-term memory owned by the caller. / "
        "ユーザー自身の指定した長期メモリを削除します。"
    ),
)
def delete_memory(payload: DeleteMemoryInput) -> dict[str, Any]:
    svc = get_memory_service()
    deleted = svc.delete_memory(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        memory_id=payload.memory_id,
    )
    return {"deleted": deleted, "memory_id": payload.memory_id}


@mcp.tool(
    name="propose_memory",
    description=(
        "Propose a long-term memory through MemoryService policy (requires human approval_id or user_confirmed=True; PII is scrubbed). / "
        "承認済またはユーザー確認済の事実のみをPIIマスキングの上で長期メモリへ記録します。"
    ),
)
def propose_memory(payload: ProposeMemoryInput) -> MemoryRecordOutput:
    svc = get_memory_service()
    item = svc.propose_memory(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        memory_type=payload.memory_type,
        topic_key=payload.topic_key,
        content=payload.content,
        lang=payload.lang,
        team_id=payload.team_id,
        approval_id=payload.approval_id,
        user_confirmed=payload.user_confirmed,
    )
    return _to_output(item)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8108))
