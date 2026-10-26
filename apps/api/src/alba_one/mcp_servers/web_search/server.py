"""FastMCP Server for `web_search` (`mcp_servers/web_search/server.py`).

JA: プロバイダ切替対応（Tavily/Brave/Firecrawl/Fake）の外部Web検索およびSSRF保護付ページ取得
EN: Pluggable external web search (Tavily/Brave/Firecrawl/Fake) and SSRF-guarded fetch_page
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-web-search")
runtime = get_server_runtime("web_search")

class SearchWebInput(BaseModel):
    """Input schema for `search_web`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")
    max_results: int = Field(default=5, ge=1, le=20)
    recency_days: int | None = Field(default=30, ge=1, le=365)


class SearchWebOutput(BaseModel):
    """Output envelope for `search_web`."""

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
    name="search_web",
    description="Search public web via configured provider (Tavily/Brave/Firecrawl/Fake) / プロバイダ切替対応（Tavily/Brave/Firecrawl/Fake）の外部Web検索",
)
def search_web(payload: SearchWebInput) -> SearchWebOutput:
    """Execute `web_search.search_web` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("web_search", "search_web", raw)
    return SearchWebOutput(**res)


class FetchPageInput(BaseModel):
    """Input schema for `fetch_page`."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class FetchPageOutput(BaseModel):
    """Output envelope for `fetch_page`."""

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
    name="fetch_page",
    description="Fetch external web page with DNS/redirect SSRF protection and guardrail scrubbing / SSRF・DNS・リダイレクト検証付の外部Webページ取得",
)
def fetch_page(payload: FetchPageInput) -> FetchPageOutput:
    """Execute `web_search.fetch_page` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("web_search", "fetch_page", raw)
    return FetchPageOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8114))
