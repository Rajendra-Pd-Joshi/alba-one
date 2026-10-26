# MCP Server: `web_search`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8114`
- **Required Env Vars**: `MCP_BEARER_TOKEN, WEB_SEARCH_PROVIDER`
- **Pyproject Extra**: `mcp-web-search`
- **Owner**: `external-intel-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: プロバイダ切替対応（Tavily/Brave/Firecrawl/Fake）の外部Web検索およびSSRF保護付ページ取得
- **EN**: Pluggable external web search (Tavily/Brave/Firecrawl/Fake) and SSRF-guarded fetch_page

## Exposed Tools (公開ツール一覧)
- **`search_web`** (`external`, required args: `['query']`): プロバイダ切替対応（Tavily/Brave/Firecrawl/Fake）の外部Web検索 / Search public web via configured provider (Tavily/Brave/Firecrawl/Fake)
- **`fetch_page`** (`external`, required args: `['url']`): SSRF・DNS・リダイレクト検証付の外部Webページ取得 / Fetch external web page with DNS/redirect SSRF protection and guardrail scrubbing

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.web_search.server --transport stdio
uv run python -m alba_one.mcp_servers.web_search.server --transport streamable-http --port 8114
```
