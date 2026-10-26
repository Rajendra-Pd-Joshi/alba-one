# MCP Server: `document_extraction`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8112`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-document-extraction`
- **Owner**: `kb-platform-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: オンプレミス文書（PDF・Excel・Word・画像）からのテキスト・表構造抽出
- **EN**: On-premise PDF, Excel, Word, and image text/table extraction

## Exposed Tools (公開ツール一覧)
- **`extract_onprem_document`** (`read`, required args: `['tenant_id', 'uri']`): オンプレミス文書（PDF/Excel/Word/画像）からのテキスト・表抽出 / Extract text and tables from on-premise PDF, Excel, Word, or image documents

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.document_extraction.server --transport stdio
uv run python -m alba_one.mcp_servers.document_extraction.server --transport streamable-http --port 8112
```
