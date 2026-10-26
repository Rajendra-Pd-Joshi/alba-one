# MCP Server: `news_search`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8115`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-news-search`
- **Owner**: `external-intel-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: 海運・物流・AI業界の公開ニュースおよび速報検索
- **EN**: Public maritime, logistics, and AI industry news search

## Exposed Tools (公開ツール一覧)
- **`search_news`** (`external`, required args: `['query']`): 海運・物流・AI業界の公開ニュース検索 / Search public maritime, logistics, and AI industry news

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.news_search.server --transport stdio
uv run python -m alba_one.mcp_servers.news_search.server --transport streamable-http --port 8115
```
