# MCP Server: `competitor_intel`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8116`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-competitor-intel`
- **Owner**: `product-strategy-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: 公開情報に基づく競合プロダクト・価格・リリース動向の追跡
- **EN**: Public-source competitor product, pricing, and release tracking

## Exposed Tools (公開ツール一覧)
- **`track_competitor_releases`** (`external`, required args: `['query']`): 公開情報に基づく競合プロダクト・リリース動向追跡 / Track competitor product releases and public positioning

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.competitor_intel.server --transport stdio
uv run python -m alba_one.mcp_servers.competitor_intel.server --transport streamable-http --port 8116
```
