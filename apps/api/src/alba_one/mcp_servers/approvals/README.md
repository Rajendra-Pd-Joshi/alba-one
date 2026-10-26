# MCP Server: `approvals`

- **Class**: `write`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8104`
- **Required Env Vars**: `MCP_BEARER_TOKEN, DATABASE_URL`
- **Pyproject Extra**: `mcp-approvals`
- **Owner**: `governance-hitl-team`
- **Data Sensitivity**: `internal_restricted`

## Purpose (目的 / 概要)
- **JA**: 人間による承認リクエスト送信・承認状態確認・未決一覧取得（HITLガードレール連携）
- **EN**: Human-in-the-loop approval request, status check, and pending queue management

## Exposed Tools (公開ツール一覧)
- **`request_approval`** (`write`, required args: `['tenant_id', 'decision_id']`): 人間による承認（HITL）リクエストの起票（write） / Submit a human-in-the-loop approval request (write)
- **`check_approval_status`** (`read`, required args: `['tenant_id', 'decision_id']`): 承認ステータスおよび付帯条件の照会 / Check approval status and attached conditions
- **`list_pending`** (`read`, required args: `['tenant_id']`): 未決承認キューの一覧取得 / List pending approval requests for a tenant

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.approvals.server --transport stdio
uv run python -m alba_one.mcp_servers.approvals.server --transport streamable-http --port 8104
```
