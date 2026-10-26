"""FastMCP Server for `news_search` (`mcp_servers/news_search/server.py`).

JA: 海運・物流・AI業界の公開ニュースおよび速報検索
EN: Public maritime, logistics, and AI industry news search
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-news-search")
runtime = get_server_runtime("news_search")

class SearchNewsInput(BaseModel):
    """Input schema for `search_news`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class SearchNewsOutput(BaseModel):
    """Output envelope for `search_news`."""

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
    name="search_news",
    description="Search public maritime, logistics, and AI industry news / 海運・物流・AI業界の公開ニュース検索",
)
def search_news(payload: SearchNewsInput) -> SearchNewsOutput:
    """Execute `news_search.search_news` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("news_search", "search_news", raw)
    return SearchNewsOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8115))
