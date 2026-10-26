"""FastAPI router for MCP Tool Catalogue (`api/tools.py`).

Exposes `/api/v1/tools` and `/api/tools` returning the registered MCP servers and tools from
`mcp_servers/registry.yaml` for the frontend and operators.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query

from alba_one.core.tenancy import get_tenant_context, get_user_context
from alba_one.mcp_client.client import discover_registered_tools
from alba_one.mcp_servers.base import load_mcp_registry
from alba_one.schemas.common import TenantContext, UserContext

router = APIRouter(tags=["tools"])


@router.get("/api/v1/tools")
@router.get("/api/tools")
async def list_mcp_tools(
    profile: str | None = Query(default=None, description="Filter by profile: core|domain|external|all"),
    agent_role: str | None = Query(default=None, description="Filter by agent allowlist"),
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return all registered MCP servers and tools with class (`read` | `write` | `external`) and profile."""
    registry = load_mcp_registry()
    tools = discover_registered_tools(agent_role=agent_role, profile_filter=profile)
    return {
        "tenant_id": tenant.tenant_id,
        "user_id": user.user_id,
        "server_count": len(registry),
        "tool_count": len(tools),
        "servers": [asdict(entry) for entry in registry.values()],
        "tools": tools,
    }
