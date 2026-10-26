"""FastMCP Server for `sql_readonly` (`mcp_servers/sql_readonly/server.py`).

JA: DBA承認済の読み取り専用ビュー（v_kb_*）に対する安全なSELECTクエリ実行
EN: Guarded read-only SQL query access against DBA-approved views (v_kb_*)
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-sql-readonly")
runtime = get_server_runtime("sql_readonly")

class QueryViewInput(BaseModel):
    """Input schema for `query_view`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    sql: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")
    max_rows: int = Field(default=100, ge=1, le=500)


class QueryViewOutput(BaseModel):
    """Output envelope for `query_view`."""

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
    name="query_view",
    description="Execute guarded read-only SELECT query on DBA-approved views (v_kb_*) / DBA承認済ビュー（v_kb_*）へのSELECT専用クエリ実行",
)
def query_view(payload: QueryViewInput) -> QueryViewOutput:
    """Execute `sql_readonly.query_view` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("sql_readonly", "query_view", raw)
    return QueryViewOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8102))
