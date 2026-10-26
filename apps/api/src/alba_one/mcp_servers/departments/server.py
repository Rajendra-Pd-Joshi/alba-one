"""FastMCP Server for `departments` (`mcp_servers/departments/server.py`).

JA: 部門別（財務・人事労務・運航・法務コンプライアンス・営業・技術）の指標と承認状況照会
EN: Read-only department facade (finance, HR, ops, legal/compliance, sales, engineering)
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-departments")
runtime = get_server_runtime("departments")

class GetDepartmentMetricsInput(BaseModel):
    """Input schema for `get_department_metrics`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    department: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetDepartmentMetricsOutput(BaseModel):
    """Output envelope for `get_department_metrics`."""

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
    name="get_department_metrics",
    description="Fetch department KPI metrics (finance, HR, ops, legal_compliance, sales, engineering) / 部門別（財務・人事・運航・法務・営業・技術）KPI指標取得",
)
def get_department_metrics(payload: GetDepartmentMetricsInput) -> GetDepartmentMetricsOutput:
    """Execute `departments.get_department_metrics` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("departments", "get_department_metrics", raw)
    return GetDepartmentMetricsOutput(**res)


class GetSignoffStatusInput(BaseModel):
    """Input schema for `get_signoff_status`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    department: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetSignoffStatusOutput(BaseModel):
    """Output envelope for `get_signoff_status`."""

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
    name="get_signoff_status",
    description="Check department sign-off status for a decision / 部門別の承認サインオフ状況照会",
)
def get_signoff_status(payload: GetSignoffStatusInput) -> GetSignoffStatusOutput:
    """Execute `departments.get_signoff_status` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("departments", "get_signoff_status", raw)
    return GetSignoffStatusOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8103))
