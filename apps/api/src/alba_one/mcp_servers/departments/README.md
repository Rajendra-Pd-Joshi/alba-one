# MCP Server: `departments`

- **Class**: `read`
- **Compose Profile**: `core`
- **Default Transport / Port**: `streamable-http` on port `8103`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-departments`
- **Owner**: `corporate-ops-team`
- **Data Sensitivity**: `internal_restricted`

## Purpose (目的 / 概要)
- **JA**: 部門別（財務・人事労務・運航・法務コンプライアンス・営業・技術）の指標と承認状況照会
- **EN**: Read-only department facade (finance, HR, ops, legal/compliance, sales, engineering)

## Exposed Tools (公開ツール一覧)
- **`get_department_metrics`** (`read`, required args: `['tenant_id', 'department']`): 部門別（財務・人事・運航・法務・営業・技術）KPI指標取得 / Fetch department KPI metrics (finance, HR, ops, legal_compliance, sales, engineering)
- **`get_signoff_status`** (`read`, required args: `['tenant_id', 'department']`): 部門別の承認サインオフ状況照会 / Check department sign-off status for a decision

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.departments.server --transport stdio
uv run python -m alba_one.mcp_servers.departments.server --transport streamable-http --port 8103
```
