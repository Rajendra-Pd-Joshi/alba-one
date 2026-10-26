"""FastMCP Server for `weather_marine` (`mcp_servers/weather_marine/server.py`).

JA: 主要港湾（東京港・横浜港・名古屋港・大阪港）の風速・波浪・気象警報参照
EN: Marine weather, gust wind speed, and port advisory lookup
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-weather-marine")
runtime = get_server_runtime("weather_marine")

class GetPortWeatherInput(BaseModel):
    """Input schema for `get_port_weather`."""

    model_config = ConfigDict(extra="forbid")

    port_code: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetPortWeatherOutput(BaseModel):
    """Output envelope for `get_port_weather`."""

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
    name="get_port_weather",
    description="Fetch marine weather, gust wind speed, and port advisories / 主要港湾の最大瞬間風速・波浪・気象警報の取得",
)
def get_port_weather(payload: GetPortWeatherInput) -> GetPortWeatherOutput:
    """Execute `weather_marine.get_port_weather` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("weather_marine", "get_port_weather", raw)
    return GetPortWeatherOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8121))
