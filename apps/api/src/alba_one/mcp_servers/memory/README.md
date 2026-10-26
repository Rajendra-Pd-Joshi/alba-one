# MCP Server: `memory`

- **Class**: `write`
- **Compose Profile**: `core`
- **Default Transport / Port**: `streamable-http` on port `8108`
- **Required Env Vars**: `MCP_BEARER_TOKEN, DATABASE_URL`
- **Pyproject Extra**: `mcp-memory`
- **Owner**: `decision-os-core-team`
- **Data Sensitivity**: `internal_restricted`

## Purpose (目的 / 概要)
- **JA**: テナント・ユーザー分離された長期メモリの検索・一覧・削除・承認済提案記録
- **EN**: Policy-gated long-term memory search, listing, deletion, and approved proposal storage

## Exposed Tools (公開ツール一覧)
- **`search_memories`** (`read`, required args: `['tenant_id', 'user_id', 'query']`): テナント・ユーザー境界内の長期メモリ検索 / Search tenant- and user-scoped long-term memories
- **`list_my_memories`** (`read`, required args: `['tenant_id', 'user_id']`): 現在のユーザーの長期メモリ一覧取得 / List active long-term memories for the current user
- **`delete_memory`** (`write`, required args: `['tenant_id', 'user_id', 'memory_id']`): 指定した長期メモリの削除（write） / Delete a user-owned long-term memory (write)
- **`propose_memory`** (`write`, required args: `['tenant_id', 'user_id', 'content']`): 承認済・確認済事実の長期メモリへのPIIマスク付記録（write） / Record an approved/confirmed memory fact with PII scrubbing (write)

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.memory.server --transport stdio
uv run python -m alba_one.mcp_servers.memory.server --transport streamable-http --port 8108
```
