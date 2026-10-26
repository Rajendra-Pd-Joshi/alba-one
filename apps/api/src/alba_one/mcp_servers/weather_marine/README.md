# MCP Server: `weather_marine`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8121`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-weather-marine`
- **Owner**: `maritime-domain-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: 主要港湾（東京港・横浜港・名古屋港・大阪港）の風速・波浪・気象警報参照
- **EN**: Marine weather, gust wind speed, and port advisory lookup

## Exposed Tools (公開ツール一覧)
- **`get_port_weather`** (`external`, required args: `['port_code']`): 主要港湾の最大瞬間風速・波浪・気象警報の取得 / Fetch marine weather, gust wind speed, and port advisories

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.weather_marine.server --transport stdio
uv run python -m alba_one.mcp_servers.weather_marine.server --transport streamable-http --port 8121
```
