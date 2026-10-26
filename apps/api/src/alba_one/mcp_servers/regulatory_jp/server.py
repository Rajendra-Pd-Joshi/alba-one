"""FastMCP Server for `regulatory_jp` (`mcp_servers/regulatory_jp/server.py`).

JA: 日本の公開法令・労務基準（36協定・改善基準告示・薬機法GDP）の参照
EN: Public Japanese regulatory lookup (Article 36 labor law, logistics & pharma GDP)
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-regulatory-jp")
runtime = get_server_runtime("regulatory_jp")

class LookupJpRegulationInput(BaseModel):
    """Input schema for `lookup_jp_regulation`."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class LookupJpRegulationOutput(BaseModel):
    """Output envelope for `lookup_jp_regulation`."""

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
    name="lookup_jp_regulation",
    description="Look up public Japanese regulations (Article 36, logistics, pharma GDP) / 日本の公開法令（36協定・改善基準告示・医薬品GDP）の参照",
)
def lookup_jp_regulation(payload: LookupJpRegulationInput) -> LookupJpRegulationOutput:
    """Execute `regulatory_jp.lookup_jp_regulation` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("regulatory_jp", "lookup_jp_regulation", raw)
    return LookupJpRegulationOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8122))
