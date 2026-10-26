# MCP Server: `staffing`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8110`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-staffing`
- **Owner**: `hr-ops-domain-team`
- **Data Sensitivity**: `internal_restricted`

## Purpose (目的 / 概要)
- **JA**: 港湾・物流要員のシフト・保有資格・36協定残業上限の適合性分析
- **EN**: Staff shift, qualification, and Article 36 overtime constraint analysis

## Exposed Tools (公開ツール一覧)
- **`analyze_staff_shifts`** (`read`, required args: `['tenant_id']`): 港湾・物流要員のシフト・保有資格・36協定残業上限の分析 / Analyze staff shifts, certifications, and Article 36 overtime limits

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.staffing.server --transport stdio
uv run python -m alba_one.mcp_servers.staffing.server --transport streamable-http --port 8110
```
