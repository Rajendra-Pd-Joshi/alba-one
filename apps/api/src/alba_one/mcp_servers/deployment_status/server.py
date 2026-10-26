"""FastMCP Server for `deployment_status` (`mcp_servers/deployment_status/server.py`).

JA: CI/CDパイプライン・カナリアロールアウト・本番環境の稼働状態照会
EN: CI/CD pipeline, canary rollout, and environment health status adapter
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-deployment-status")
runtime = get_server_runtime("deployment_status")

class GetEnvironmentStatusInput(BaseModel):
    """Input schema for `get_environment_status`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    environment: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetEnvironmentStatusOutput(BaseModel):
    """Output envelope for `get_environment_status`."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    mcp_server: str
    tool_name: str
    tool_class: str
    external: bool
    latency_ms: float
    data: dict[str, Any]
    audit: dict[str, Any]


@mcp.tool(
    name="get_environment_status",
    description="Check CI/CD pipeline, canary rollout, and environment health status / CI/CDパイプライン・カナリアロールアウト・本番稼働状態の照会",
)
def get_environment_status(payload: GetEnvironmentStatusInput) -> GetEnvironmentStatusOutput:
    """Execute `deployment_status.get_environment_status` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("deployment_status", "get_environment_status", raw)
    return GetEnvironmentStatusOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8113))
