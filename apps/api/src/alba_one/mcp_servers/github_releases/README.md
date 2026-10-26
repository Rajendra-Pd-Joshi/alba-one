# MCP Server: `github_releases`

- **Class**: `external`
- **Compose Profile**: `external`
- **Default Transport / Port**: `streamable-http` on port `8119`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-github-releases`
- **Owner**: `sre-platform-team`
- **Data Sensitivity**: `public_external`

## Purpose (目的 / 概要)
- **JA**: OSSおよび関連リポジトリの公開リリースノート・変更履歴取得
- **EN**: Public OSS repository release notes and changelog lookup

## Exposed Tools (公開ツール一覧)
- **`list_repo_releases`** (`external`, required args: `['repo']`): 公開GitHubリポジトリのリリースノート取得 / List public GitHub repository release notes and changelogs

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.github_releases.server --transport stdio
uv run python -m alba_one.mcp_servers.github_releases.server --transport streamable-http --port 8119
```
