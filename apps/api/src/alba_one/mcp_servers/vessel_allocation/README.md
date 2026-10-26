# MCP Server: `vessel_allocation`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8111`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-vessel-allocation`
- **Owner**: `maritime-domain-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: 船舶ETA・バース水深制約・優先貨物（医薬品定温コンテナ）の着岸割当分析
- **EN**: Vessel berth allocation, draft constraint, and priority cargo analysis

## Exposed Tools (公開ツール一覧)
- **`analyze_berth_allocation`** (`read`, required args: `['tenant_id']`): 船舶ETA・バース水深制約・優先貨物の着岸割当分析 / Analyze vessel ETA, berth draft constraints, and priority cargo allocation

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.vessel_allocation.server --transport stdio
uv run python -m alba_one.mcp_servers.vessel_allocation.server --transport streamable-http --port 8111
```
