"""FastMCP Server for `github_releases` (`mcp_servers/github_releases/server.py`).

JA: OSSおよび関連リポジトリの公開リリースノート・変更履歴取得
EN: Public OSS repository release notes and changelog lookup
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-github-releases")
runtime = get_server_runtime("github_releases")

class ListRepoReleasesInput(BaseModel):
    """Input schema for `list_repo_releases`."""

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(..., min_length=1)
    tenant_id: str = Field(default="tenant_alba_demo", min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class ListRepoReleasesOutput(BaseModel):
    """Output envelope for `list_repo_releases`."""

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
    name="list_repo_releases",
    description="List public GitHub repository release notes and changelogs / 公開GitHubリポジトリのリリースノート取得",
)
def list_repo_releases(payload: ListRepoReleasesInput) -> ListRepoReleasesOutput:
    """Execute `github_releases.list_repo_releases` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("github_releases", "list_repo_releases", raw)
    return ListRepoReleasesOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8119))
