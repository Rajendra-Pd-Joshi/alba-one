"""FastMCP Server for `competitor_intel` (`mcp_servers/competitor_intel/server.py`).

JA: 公開情報に基づく競合プロダクト・価格・リリース動向の追跡
EN: Public-source competitor product, pricing, and release tracking
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-competitor-intel")
runtime = get_server_runtime("competitor_intel")

class TrackCompetitorReleasesInput(BaseModel):
    """Input schema for `track_competitor_releases`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class TrackCompetitorReleasesOutput(BaseModel):
    """Output envelope for `track_competitor_releases`."""

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
    name="track_competitor_releases",
    description="Track competitor product releases and public positioning / 公開情報に基づく競合プロダクト・リリース動向追跡",
)
def track_competitor_releases(payload: TrackCompetitorReleasesInput) -> TrackCompetitorReleasesOutput:
    """Execute `competitor_intel.track_competitor_releases` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("competitor_intel", "track_competitor_releases", raw)
    return TrackCompetitorReleasesOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8116))
