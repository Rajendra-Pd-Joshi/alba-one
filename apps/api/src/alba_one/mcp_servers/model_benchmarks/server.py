"""FastMCP Server for `model_benchmarks` (`mcp_servers/model_benchmarks/server.py`).

JA: 公開リーダーボードおよび他社モデルのベンチマーク指標・評価条件の注記付取得
EN: Public model benchmark leaderboards with evaluation-setup caveats
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-model-benchmarks")
runtime = get_server_runtime("model_benchmarks")

class LookupPublicBenchmarksInput(BaseModel):
    """Input schema for `lookup_public_benchmarks`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class LookupPublicBenchmarksOutput(BaseModel):
    """Output envelope for `lookup_public_benchmarks`."""

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
    name="lookup_public_benchmarks",
    description="Look up public model benchmark leaderboards with evaluation-setup caveats / 公開リーダーボード指標および評価条件の注記（caveats）取得",
)
def lookup_public_benchmarks(payload: LookupPublicBenchmarksInput) -> LookupPublicBenchmarksOutput:
    """Execute `model_benchmarks.lookup_public_benchmarks` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("model_benchmarks", "lookup_public_benchmarks", raw)
    return LookupPublicBenchmarksOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8117))
