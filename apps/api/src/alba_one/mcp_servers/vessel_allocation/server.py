"""FastMCP Server for `vessel_allocation` (`mcp_servers/vessel_allocation/server.py`).

JA: 船舶ETA・バース水深制約・優先貨物（医薬品定温コンテナ）の着岸割当分析
EN: Vessel berth allocation, draft constraint, and priority cargo analysis
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-vessel-allocation")
runtime = get_server_runtime("vessel_allocation")

class AnalyzeBerthAllocationInput(BaseModel):
    """Input schema for `analyze_berth_allocation`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class AnalyzeBerthAllocationOutput(BaseModel):
    """Output envelope for `analyze_berth_allocation`."""

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
    name="analyze_berth_allocation",
    description="Analyze vessel ETA, berth draft constraints, and priority cargo allocation / 船舶ETA・バース水深制約・優先貨物の着岸割当分析",
)
def analyze_berth_allocation(payload: AnalyzeBerthAllocationInput) -> AnalyzeBerthAllocationOutput:
    """Execute `vessel_allocation.analyze_berth_allocation` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("vessel_allocation", "analyze_berth_allocation", raw)
    return AnalyzeBerthAllocationOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8111))
