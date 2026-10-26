# MCP Server: `experiment_tracking`

- **Class**: `read`
- **Compose Profile**: `domain`
- **Default Transport / Port**: `streamable-http` on port `8105`
- **Required Env Vars**: `MCP_BEARER_TOKEN`
- **Pyproject Extra**: `mcp-experiment-tracking`
- **Owner**: `ml-platform-team`
- **Data Sensitivity**: `internal_confidential`

## Purpose (目的 / 概要)
- **JA**: MLflow互換の実験一覧・実行メトリクス・ラン比較・モデルバージョン・リリース準備状況照会
- **EN**: MLflow-compatible adapter for experiments, runs, comparisons, versions, and release readiness

## Exposed Tools (公開ツール一覧)
- **`list_experiments`** (`read`, required args: `['tenant_id']`): MLflow互換の実験一覧取得 / List MLflow-compatible model experiments
- **`get_run`** (`read`, required args: `['tenant_id', 'experiment_id']`): 指定した実験ランの評価メトリクス取得 / Get evaluation metrics for a specific experiment run
- **`compare_runs`** (`read`, required args: `['tenant_id', 'baseline_id', 'candidate_id']`): ベースラインと候補ランのメトリクス差分比較 / Compare metrics between baseline and candidate runs
- **`get_model_versions`** (`read`, required args: `['tenant_id', 'model_family']`): モデルファミリー別の登録バージョン一覧取得 / List registered versions for a model family
- **`get_release_readiness_summary`** (`read`, required args: `['tenant_id', 'version_tag']`): モデルバージョンのカナリアリリース準備状況サマリ取得 / Get canary release readiness summary for a model version

## Security & Guardrails
- Protected by bearer token verification (`MCP_BEARER_TOKEN`) and Layer 5 Tool Guardrail (`guardrails/tool_layer.py`).
- Outbound queries on `external` servers pass through `guardrails/outbound_query.py` (`OUTBOUND_QUERY_POLICY=block|generalize`).
- All calls are logged to the `tool_calls` audit table with `tool_call_id`, `tenant_id`, `mcp_server`, `tool_name`, `latency_ms`, and `side_effecting`.

## Run Locally
```bash
uv run python -m alba_one.mcp_servers.experiment_tracking.server --transport stdio
uv run python -m alba_one.mcp_servers.experiment_tracking.server --transport streamable-http --port 8105
```
