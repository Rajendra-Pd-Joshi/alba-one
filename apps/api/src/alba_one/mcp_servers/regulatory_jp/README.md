# MCP Server: `regulatory_jp`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8122`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-regulatory-jp`
- **Owner**: `legal-compliance-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: 日本の公開法令・労務基準（36協定・改善基準告示・薬機法GDP）の参照
- **EN**: Public Japanese regulatory lookup (Article 36 labor law, logistics & pharma GDP)

## Exposed Tools (公開ツール一覧)
- **`lookup_jp_regulation`** (`external`, required args: `['topic']`): 日本の公開法令（36協定・改善基準告示・医薬品GDP）の参照 / Look up public Japanese regulations (Article 36, logistics, pharma GDP)

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.regulatory_jp.server --transport stdio
uv run python -m alba_one.mcp_servers.regulatory_jp.server --transport streamable-http --port 8122
```
