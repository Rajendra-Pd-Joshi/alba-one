# MCP Server: `market_data`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8120`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-market-data`
- **Owner**: `finance-domain-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: 為替（USD/JPY）・燃料価格・海上コンテナ運賃指数の参照
- **EN**: FX (USD/JPY), bunker fuel, and container freight index lookup

## Exposed Tools (公開ツール一覧)
- **`get_market_indices`** (`external`, required args: `['index_code']`): 為替（USD/JPY）・バンカー燃料・海上運賃指数の取得 / Fetch FX (USD/JPY), bunker fuel, and container freight market indices

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.market_data.server --transport stdio
uv run python -m alba_one.mcp_servers.market_data.server --transport streamable-http --port 8120
```
