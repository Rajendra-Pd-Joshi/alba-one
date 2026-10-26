# MCP Server: `delivery_planning`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8109`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-delivery-planning`
- **Owner**: `logistics-domain-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: 配送ルート・定温車両積載容量・SLA期限の適合性分析
- **EN**: Delivery route, vehicle payload capacity, and cold-chain SLA analysis

## Exposed Tools (公開ツール一覧)
- **`analyze_delivery_routes`** (`read`, required args: `['tenant_id']`): 配送ルート・定温車両容量・SLA期限の適合性分析 / Analyze delivery routes, cold-chain vehicle capacity, and SLA deadlines

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.delivery_planning.server --transport stdio
uv run python -m alba_one.mcp_servers.delivery_planning.server --transport streamable-http --port 8109
```
