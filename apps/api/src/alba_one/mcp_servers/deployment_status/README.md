# MCP Server: `deployment_status`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8113`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-deployment-status`
- **Owner**: `sre-platform-team`
- **Data Sensitivity**: `internal_operational`

## Purpose (目的 / 概要)
- **JA**: CI/CDパイプライン・カナリアロールアウト・本番環境の稼働状態照会
- **EN**: CI/CD pipeline, canary rollout, and environment health status adapter

## Exposed Tools (公開ツール一覧)
- **`get_environment_status`** (`read`, required args: `['tenant_id', 'environment']`): CI/CDパイプライン・カナリアロールアウト・本番稼働状態の照会 / Check CI/CD pipeline, canary rollout, and environment health status

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.deployment_status.server --transport stdio
uv run python -m alba_one.mcp_servers.deployment_status.server --transport streamable-http --port 8113
```
