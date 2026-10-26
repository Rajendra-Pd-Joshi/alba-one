"""FastMCP Server for `approvals` (`mcp_servers/approvals/server.py`).

JA: 人間による承認リクエスト送信・承認状態確認・未決一覧取得（HITLガードレール連携）
EN: Human-in-the-loop approval request, status check, and pending queue management
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-approvals")
runtime = get_server_runtime("approvals")

class RequestApprovalInput(BaseModel):
    """Input schema for `request_approval`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")
    approval_id: str | None = Field(default=None)
    user_confirmed: bool = Field(default=False)


class RequestApprovalOutput(BaseModel):
    """Output envelope for `request_approval`."""

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
    name="request_approval",
    description="Submit a human-in-the-loop approval request (write) / 人間による承認（HITL）リクエストの起票（write）",
)
def request_approval(payload: RequestApprovalInput) -> RequestApprovalOutput:
    """Execute `approvals.request_approval` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool(
        "approvals", "request_approval", raw,
        approval_id=payload.approval_id, user_confirmed=payload.user_confirmed,
    )
    return RequestApprovalOutput(**res)


class CheckApprovalStatusInput(BaseModel):
    """Input schema for `check_approval_status`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class CheckApprovalStatusOutput(BaseModel):
    """Output envelope for `check_approval_status`."""

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
    name="check_approval_status",
    description="Check approval status and attached conditions / 承認ステータスおよび付帯条件の照会",
)
def check_approval_status(payload: CheckApprovalStatusInput) -> CheckApprovalStatusOutput:
    """Execute `approvals.check_approval_status` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("approvals", "check_approval_status", raw)
    return CheckApprovalStatusOutput(**res)


class ListPendingInput(BaseModel):
    """Input schema for `list_pending`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class ListPendingOutput(BaseModel):
    """Output envelope for `list_pending`."""

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
    name="list_pending",
    description="List pending approval requests for a tenant / 未決承認キューの一覧取得",
)
def list_pending(payload: ListPendingInput) -> ListPendingOutput:
    """Execute `approvals.list_pending` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("approvals", "list_pending", raw)
    return ListPendingOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8104))
