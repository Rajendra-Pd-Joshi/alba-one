# MCP Server: `knowledge_base`

- **Class**: `read`
- **Compose Profile**: `core`
- **Default Transport / Port**: `streamable-http` on port `8101`
- **Required Env Vars**: `MCP_BEARER_TOKEN, DATABASE_URL, PINECONE_API_KEY`
- **Pyproject Extra**: `mcp-knowledge-base`
- **Owner**: `kb-platform-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: オンプレミスPostgreSQL＋PineconeからのACLフィルタ付ナレッジ検索・エンティティ参照
- **EN**: ACL-filtered hybrid KB search and business ontology entity lookup

## Exposed Tools (公開ツール一覧)
- **`kb_search`** (`read`, required args: `['tenant_id', 'query']`): ACLフィルタ付ハイブリッドKB検索 / ACL-filtered hybrid KB search
- **`kb_get_chunk`** (`read`, required args: `['tenant_id', 'chunk_id']`): chunk_idによるオンプレチャンク取得 / Retrieve on-prem KB chunk by chunk_id
- **`kb_get_entity`** (`read`, required args: `['tenant_id', 'entity_type']`): 業務エンティティのオントロジー定義取得 / Inspect business entity ontology metadata
- **`kb_list_entities`** (`read`, required args: `['tenant_id']`): アクセス可能な業務エンティティ一覧取得 / List ACL-visible business entities

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.knowledge_base.server --transport stdio
uv run python -m alba_one.mcp_servers.knowledge_base.server --transport streamable-http --port 8101
```
