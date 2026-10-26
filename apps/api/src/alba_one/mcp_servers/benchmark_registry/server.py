"""FastMCP Server for `benchmark_registry` (`mcp_servers/benchmark_registry/server.py`).

JA: 社内ベンチマーク評価結果およびモデルバージョン間のリグレッション比較
EN: Internal benchmark registry and cross-version regression comparisons
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-benchmark-registry")
runtime = get_server_runtime("benchmark_registry")

class GetBenchmarkResultsInput(BaseModel):
    """Input schema for `get_benchmark_results`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    version_tag: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetBenchmarkResultsOutput(BaseModel):
    """Output envelope for `get_benchmark_results`."""

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
    name="get_benchmark_results",
    description="Fetch internal benchmark suite evaluation scores / 社内ベンチマークスイート評価結果の取得",
)
def get_benchmark_results(payload: GetBenchmarkResultsInput) -> GetBenchmarkResultsOutput:
    """Execute `benchmark_registry.get_benchmark_results` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("benchmark_registry", "get_benchmark_results", raw)
    return GetBenchmarkResultsOutput(**res)


class CompareRegressionsInput(BaseModel):
    """Input schema for `compare_regressions`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    baseline_tag: str = Field(..., min_length=1)
    candidate_tag: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class CompareRegressionsOutput(BaseModel):
    """Output envelope for `compare_regressions`."""

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
    name="compare_regressions",
    description="Compare benchmark regressions across model versions / バージョン間のベンチマークリグレッション有無の比較",
)
def compare_regressions(payload: CompareRegressionsInput) -> CompareRegressionsOutput:
    """Execute `benchmark_registry.compare_regressions` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("benchmark_registry", "compare_regressions", raw)
    return CompareRegressionsOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8106))
