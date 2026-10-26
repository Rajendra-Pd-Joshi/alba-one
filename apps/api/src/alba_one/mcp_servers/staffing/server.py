"""FastMCP Server for `staffing` (`mcp_servers/staffing/server.py`).

JA: 港湾・物流要員のシフト・保有資格・36協定残業上限の適合性分析
EN: Staff shift, qualification, and Article 36 overtime constraint analysis
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-staffing")
runtime = get_server_runtime("staffing")

class AnalyzeStaffShiftsInput(BaseModel):
    """Input schema for `analyze_staff_shifts`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class AnalyzeStaffShiftsOutput(BaseModel):
    """Output envelope for `analyze_staff_shifts`."""

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
    name="analyze_staff_shifts",
    description="Analyze staff shifts, certifications, and Article 36 overtime limits / 港湾・物流要員のシフト・保有資格・36協定残業上限の分析",
)
def analyze_staff_shifts(payload: AnalyzeStaffShiftsInput) -> AnalyzeStaffShiftsOutput:
    """Execute `staffing.analyze_staff_shifts` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("staffing", "analyze_staff_shifts", raw)
    return AnalyzeStaffShiftsOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8110))
