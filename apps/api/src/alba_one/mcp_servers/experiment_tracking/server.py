"""FastMCP Server for `experiment_tracking` (`mcp_servers/experiment_tracking/server.py`).

JA: MLflow互換の実験一覧・実行メトリクス・ラン比較・モデルバージョン・リリース準備状況照会
EN: MLflow-compatible adapter for experiments, runs, comparisons, versions, and release readiness
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-experiment-tracking")
runtime = get_server_runtime("experiment_tracking")

class ListExperimentsInput(BaseModel):
    """Input schema for `list_experiments`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class ListExperimentsOutput(BaseModel):
    """Output envelope for `list_experiments`."""

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
    name="list_experiments",
    description="List MLflow-compatible model experiments / MLflow互換の実験一覧取得",
)
def list_experiments(payload: ListExperimentsInput) -> ListExperimentsOutput:
    """Execute `experiment_tracking.list_experiments` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("experiment_tracking", "list_experiments", raw)
    return ListExperimentsOutput(**res)


class GetRunInput(BaseModel):
    """Input schema for `get_run`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    experiment_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetRunOutput(BaseModel):
    """Output envelope for `get_run`."""

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
    name="get_run",
    description="Get evaluation metrics for a specific experiment run / 指定した実験ランの評価メトリクス取得",
)
def get_run(payload: GetRunInput) -> GetRunOutput:
    """Execute `experiment_tracking.get_run` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("experiment_tracking", "get_run", raw)
    return GetRunOutput(**res)


class CompareRunsInput(BaseModel):
    """Input schema for `compare_runs`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    baseline_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class CompareRunsOutput(BaseModel):
    """Output envelope for `compare_runs`."""

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
    name="compare_runs",
    description="Compare metrics between baseline and candidate runs / ベースラインと候補ランのメトリクス差分比較",
)
def compare_runs(payload: CompareRunsInput) -> CompareRunsOutput:
    """Execute `experiment_tracking.compare_runs` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("experiment_tracking", "compare_runs", raw)
    return CompareRunsOutput(**res)


class GetModelVersionsInput(BaseModel):
    """Input schema for `get_model_versions`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    model_family: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetModelVersionsOutput(BaseModel):
    """Output envelope for `get_model_versions`."""

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
    name="get_model_versions",
    description="List registered versions for a model family / モデルファミリー別の登録バージョン一覧取得",
)
def get_model_versions(payload: GetModelVersionsInput) -> GetModelVersionsOutput:
    """Execute `experiment_tracking.get_model_versions` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("experiment_tracking", "get_model_versions", raw)
    return GetModelVersionsOutput(**res)


class GetReleaseReadinessSummaryInput(BaseModel):
    """Input schema for `get_release_readiness_summary`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    version_tag: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetReleaseReadinessSummaryOutput(BaseModel):
    """Output envelope for `get_release_readiness_summary`."""

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
    name="get_release_readiness_summary",
    description="Get canary release readiness summary for a model version / モデルバージョンのカナリアリリース準備状況サマリ取得",
)
def get_release_readiness_summary(payload: GetReleaseReadinessSummaryInput) -> GetReleaseReadinessSummaryOutput:
    """Execute `experiment_tracking.get_release_readiness_summary` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("experiment_tracking", "get_release_readiness_summary", raw)
    return GetReleaseReadinessSummaryOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8105))
