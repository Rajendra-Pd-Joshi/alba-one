"""FastMCP Server for `decision_history` (`mcp_servers/decision_history/server.py`).

JA: 過去の意思決定・仮説・承認条件・成果レビューの検索および類似案件照会
EN: Past decisions, hypotheses, approvals, and outcome review similarity search
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-decision-history")
runtime = get_server_runtime("decision_history")

class SearchSimilarDecisionsInput(BaseModel):
    """Input schema for `search_similar_decisions`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class SearchSimilarDecisionsOutput(BaseModel):
    """Output envelope for `search_similar_decisions`."""

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
    name="search_similar_decisions",
    description="Search past decisions, approval conditions, and outcome reviews / 類似する過去の意思決定・承認条件・成果レビューの検索",
)
def search_similar_decisions(payload: SearchSimilarDecisionsInput) -> SearchSimilarDecisionsOutput:
    """Execute `decision_history.search_similar_decisions` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("decision_history", "search_similar_decisions", raw)
    return SearchSimilarDecisionsOutput(**res)


class GetDecisionRecordInput(BaseModel):
    """Input schema for `get_decision_record`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class GetDecisionRecordOutput(BaseModel):
    """Output envelope for `get_decision_record`."""

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
    name="get_decision_record",
    description="Retrieve a full decision record by decision_id / 特定の意思決定レコード詳細取得",
)
def get_decision_record(payload: GetDecisionRecordInput) -> GetDecisionRecordOutput:
    """Execute `decision_history.get_decision_record` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("decision_history", "get_decision_record", raw)
    return GetDecisionRecordOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8107))
