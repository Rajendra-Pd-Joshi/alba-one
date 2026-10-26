# MCP Server: `sql_readonly`

- **Class**: `read`
- **Compose Profile**: `core`
- **Default Transport / Port**: `streamable-http` on port `8102`
- **Required Env Vars**: `MCP_BEARER_TOKEN, DATABASE_URL`
- **Pyproject Extra**: `mcp-sql-readonly`
- **Owner**: `data-engineering-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: DBA承認済の読み取り専用ビュー（v_kb_*）に対する安全なSELECTクエリ実行
- **EN**: Guarded read-only SQL query access against DBA-approved views (v_kb_*)

## Exposed Tools (公開ツール一覧)
- **`query_view`** (`read`, required args: `['tenant_id', 'sql']`): DBA承認済ビュー（v_kb_*）へのSELECT専用クエリ実行 / Execute guarded read-only SELECT query on DBA-approved views (v_kb_*)

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.sql_readonly.server --transport stdio
uv run python -m alba_one.mcp_servers.sql_readonly.server --transport streamable-http --port 8102
```
