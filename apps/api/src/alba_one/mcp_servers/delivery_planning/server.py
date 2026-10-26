"""FastMCP Server for `delivery_planning` (`mcp_servers/delivery_planning/server.py`).

JA: 配送ルート・定温車両積載容量・SLA期限の適合性分析
EN: Delivery route, vehicle payload capacity, and cold-chain SLA analysis
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-delivery-planning")
runtime = get_server_runtime("delivery_planning")

class AnalyzeDeliveryRoutesInput(BaseModel):
    """Input schema for `analyze_delivery_routes`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class AnalyzeDeliveryRoutesOutput(BaseModel):
    """Output envelope for `analyze_delivery_routes`."""

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
    name="analyze_delivery_routes",
    description="Analyze delivery routes, cold-chain vehicle capacity, and SLA deadlines / 配送ルート・定温車両容量・SLA期限の適合性分析",
)
def analyze_delivery_routes(payload: AnalyzeDeliveryRoutesInput) -> AnalyzeDeliveryRoutesOutput:
    """Execute `delivery_planning.analyze_delivery_routes` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("delivery_planning", "analyze_delivery_routes", raw)
    return AnalyzeDeliveryRoutesOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8109))
