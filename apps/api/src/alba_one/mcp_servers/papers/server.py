"""FastMCP Server for `papers` (`mcp_servers/papers/server.py`).

JA: arXiv / Semantic Scholar 等の公開技術論文検索
EN: Academic paper search across arXiv and Semantic Scholar
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-papers")
runtime = get_server_runtime("papers")

class SearchPapersInput(BaseModel):
    """Input schema for `search_papers`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class SearchPapersOutput(BaseModel):
    """Output envelope for `search_papers`."""

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
    name="search_papers",
    description="Search public technical papers on arXiv and Semantic Scholar / arXiv / Semantic Scholar 等の公開技術論文検索",
)
def search_papers(payload: SearchPapersInput) -> SearchPapersOutput:
    """Execute `papers.search_papers` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("papers", "search_papers", raw)
    return SearchPapersOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8118))
