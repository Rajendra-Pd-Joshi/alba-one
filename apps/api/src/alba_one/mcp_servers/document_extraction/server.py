"""FastMCP Server for `document_extraction` (`mcp_servers/document_extraction/server.py`).

JA: オンプレミス文書（PDF・Excel・Word・画像）からのテキスト・表構造抽出
EN: On-premise PDF, Excel, Word, and image text/table extraction
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from alba_one.mcp_servers.base import run_mcp_server_cli
from alba_one.mcp_servers.handlers import get_server_runtime, invoke_mcp_tool

mcp = FastMCP("alba-document-extraction")
runtime = get_server_runtime("document_extraction")

class ExtractOnpremDocumentInput(BaseModel):
    """Input schema for `extract_onprem_document`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    uri: str = Field(..., min_length=1)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


class ExtractOnpremDocumentOutput(BaseModel):
    """Output envelope for `extract_onprem_document`."""

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
    name="extract_onprem_document",
    description="Extract text and tables from on-premise PDF, Excel, Word, or image documents / オンプレミス文書（PDF/Excel/Word/画像）からのテキスト・表抽出",
)
def extract_onprem_document(payload: ExtractOnpremDocumentInput) -> ExtractOnpremDocumentOutput:
    """Execute `document_extraction.extract_onprem_document` through `MCPServerAuditRuntime`."""
    raw = payload.model_dump()
    res = invoke_mcp_tool("document_extraction", "extract_onprem_document", raw)
    return ExtractOnpremDocumentOutput(**res)


if __name__ == "__main__":
    raise SystemExit(run_mcp_server_cli(mcp, default_port=8112))
