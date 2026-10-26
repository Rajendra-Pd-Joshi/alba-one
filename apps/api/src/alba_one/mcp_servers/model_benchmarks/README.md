# MCP Server: `model_benchmarks`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8117`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-model-benchmarks`
- **Owner**: `ml-quality-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: 公開リーダーボードおよび他社モデルのベンチマーク指標・評価条件の注記付取得
- **EN**: Public model benchmark leaderboards with evaluation-setup caveats

## Exposed Tools (公開ツール一覧)
- **`lookup_public_benchmarks`** (`external`, required args: `['query']`): 公開リーダーボード指標および評価条件の注記（caveats）取得 / Look up public model benchmark leaderboards with evaluation-setup caveats

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.model_benchmarks.server --transport stdio
uv run python -m alba_one.mcp_servers.model_benchmarks.server --transport streamable-http --port 8117
```
