# MCP Server: `decision_history`

- **Class**: `read`
- **Compose Profile**: `core`
- **Default Transport / Port**: `streamable-http` on port `8107`
- **Required Env Vars**: `MCP_BEARER_TOKEN, DATABASE_URL`
- **Pyproject Extra**: `mcp-decision-history`
- **Owner**: `decision-os-core-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: 過去の意思決定・仮説・承認条件・成果レビューの検索および類似案件照会
- **EN**: Past decisions, hypotheses, approvals, and outcome review similarity search

## Exposed Tools (公開ツール一覧)
- **`search_similar_decisions`** (`read`, required args: `['tenant_id', 'query']`): 類似する過去の意思決定・承認条件・成果レビューの検索 / Search past decisions, approval conditions, and outcome reviews
- **`get_decision_record`** (`read`, required args: `['tenant_id', 'decision_id']`): 特定の意思決定レコード詳細取得 / Retrieve a full decision record by decision_id

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.decision_history.server --transport stdio
uv run python -m alba_one.mcp_servers.decision_history.server --transport streamable-http --port 8107
```
