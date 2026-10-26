"""FastMCP Server for `market_data` (`mcp_servers/market_data/server.py`).

JA: 為替（USD/JPY）・燃料価格・海上コンテナ運賃指数の参照
EN: FX (USD/JPY), bunker fuel, and container freight index lookup
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-market-data")
runtime = get_server_runtime("market_data")

class GetMarketIndicesInput(BaseModel):
    """Input schema for `get_market_indices`."""

    model_config = ConfigDict(extra="forbid")

    index_code: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetMarketIndicesOutput(BaseModel):
    """Output envelope for `get_market_indices`."""

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
    name="get_market_indices",
    description="Fetch FX (USD/JPY), bunker fuel, and container freight market indices / 為替（USD/JPY）・バンカー燃料・海上運賃指数の取得",
)
def get_market_indices(payload: GetMarketIndicesInput) -> GetMarketIndicesOutput:
    """Execute `market_data.get_market_indices` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("market_data", "get_market_indices", raw)
    return GetMarketIndicesOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8120))
