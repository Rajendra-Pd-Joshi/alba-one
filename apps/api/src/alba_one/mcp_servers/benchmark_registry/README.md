# MCP Server: `benchmark_registry`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8106`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-benchmark-registry`
- **Owner**: `ml-quality-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: 社内ベンチマーク評価結果およびモデルバージョン間のリグレッション比較
- **EN**: Internal benchmark registry and cross-version regression comparisons

## Exposed Tools (公開ツール一覧)
- **`get_benchmark_results`** (`read`, required args: `['tenant_id', 'version_tag']`): 社内ベンチマークスイート評価結果の取得 / Fetch internal benchmark suite evaluation scores
- **`compare_regressions`** (`read`, required args: `['tenant_id', 'baseline_tag', 'candidate_tag']`): バージョン間のベンチマークリグレッション有無の比較 / Compare benchmark regressions across model versions

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.benchmark_registry.server --transport stdio
uv run python -m alba_one.mcp_servers.benchmark_registry.server --transport streamable-http --port 8106
```
