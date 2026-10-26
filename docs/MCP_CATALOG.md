# ALBA ONE — MCP Server Catalogue (`docs/MCP_CATALOG.md`)

Generated from the single source of truth: `apps/api/src/alba_one/mcp_servers/registry.yaml`.
Per **Principle 1 (MCP over tools/APIs)**, every capability the planner uses is exposed as a FastMCP server and consumed via `langchain-mcp-adapters` (`MultiServerMCPClient`).

## 1. Complete MCP Server Table (22 Servers)

| # | Server Name | Class | Profile | Port | Image Extra (`Dockerfile.mcp`) | Data Sensitivity | Owner | Purpose (JP / EN) |
| :- | :--- | :--- | :--- | ---: | :--- | :--- | :--- | :--- |
| 1 | `knowledge_base` | `read` | `core` | 8101 | `mcp-knowledge-base` | `internal_confidential` | `kb-platform-team` | オンプレミスPostgreSQL＋PineconeからのACLフィルタ付ナレッジ検索 / ACL-filtered hybrid KB search & ontology entity lookup |
| 2 | `sql_readonly` | `read` | `core` | 8102 | `mcp-sql-readonly` | `internal_confidential` | `data-engineering-team` | DBA承認済ビュー（`v_kb_*`）への読み取り専用SQL実行 / Guarded read-only SQL access to DBA-approved views |
| 3 | `departments` | `read` | `core` | 8103 | `mcp-departments` | `internal_restricted` | `corporate-ops-team` | 部門別（財務・人事・運航・法務・営業・技術）指標と承認状況照会 / Read-only facade per department |
| 4 | `approvals` | `write` | `domain` | 8104 | `mcp-approvals` | `internal_restricted` | `governance-hitl-team` | HITL承認リクエスト送信・状態確認・未決一覧取得 / HITL approval requests, status checks & pending queue |
| 5 | `experiment_tracking` | `read` | `domain` | 8105 | `mcp-experiment-tracking` | `internal_confidential` | `ml-platform-team` | MLflow互換の実験・実行メトリクス・ラン比較・リリース準備状況照会 / MLflow adapter for experiments, runs & release readiness |
| 6 | `benchmark_registry` | `read` | `domain` | 8106 | `mcp-benchmark-registry` | `internal_confidential` | `ml-quality-team` | 社内ベンチマーク結果・バージョン間リグレッション比較 / Internal benchmark results & regression comparisons |
| 7 | `decision_history` | `read` | `core` | 8107 | `mcp-decision-history` | `internal_confidential` | `decision-os-core-team` | 過去の意思決定・仮説・承認条件・成果レビューの類似検索 / Past decisions, hypotheses, approvals & outcomes search |
| 8 | `memory` | `write` | `core` | 8108 | `mcp-memory` | `internal_restricted` | `decision-os-core-team` | ポリシー制御付の長期メモリ検索・一覧・削除・提案記録 / Policy-gated long-term memory search, list, delete & propose |
| 9 | `delivery_planning` | `read` | `domain` | 8109 | `mcp-delivery-planning` | `internal_confidential` | `logistics-domain-team` | 配送ルート・定温車両積載容量・SLA期限の適合性分析 / Delivery route, payload & cold-chain SLA analysis |
| 10 | `staffing` | `read` | `domain` | 8110 | `mcp-staffing` | `internal_restricted` | `hr-ops-domain-team` | 港湾・物流要員のシフト・資格・36協定残業上限分析 / Staff shift, skill & Article 36 overtime analysis |
| 11 | `vessel_allocation` | `read` | `domain` | 8111 | `mcp-vessel-allocation` | `internal_confidential` | `maritime-domain-team` | 船舶ETA・バース水深制約・優先貨物着岸割当分析 / Vessel berth, ETA, draft & priority cargo analysis |
| 12 | `document_extraction` | `read` | `domain` | 8112 | `mcp-document-extraction` | `internal_confidential` | `kb-platform-team` | オンプレミス文書（PDF・Excel・Word・画像）抽出 / On-premise PDF/Excel/Word/image extraction |
| 13 | `deployment_status` | `read` | `domain` | 8113 | `mcp-deployment-status` | `internal_operational` | `sre-platform-team` | CI/CD・カナリアロールアウト・環境ステータス照会 / CI/CD and environment status adapter |
| 14 | `web_search` | `external` | `external` | 8114 | `mcp-web-search` | `public_external` | `external-intel-team` | プロバイダ切替対応（Tavily/Brave/Firecrawl/Fake）Web検索＋`fetch_page` / Pluggable web search + SSRF-guarded `fetch_page` |
| 15 | `news_search` | `external` | `external` | 8115 | `mcp-news-search` | `public_external` | `external-intel-team` | 海運・物流・AI業界の公開ニュース検索 / Public maritime, logistics & AI news search |
| 16 | `competitor_intel` | `external` | `external` | 8116 | `mcp-competitor-intel` | `public_external` | `product-strategy-team` | 公開情報に基づく競合製品・価格・リリース追跡 / Public-source competitor product/pricing/release tracking |
| 17 | `model_benchmarks` | `external` | `external` | 8117 | `mcp-model-benchmarks` | `public_external` | `ml-quality-team` | 公開リーダーボード・他社モデル指標（評価条件注記付） / Public model leaderboards with evaluation-setup caveats |
| 18 | `papers` | `external` | `external` | 8118 | `mcp-papers` | `public_external` | `research-team` | arXiv / Semantic Scholar 公開技術論文検索 / Academic paper lookup (arXiv / Semantic Scholar) |
| 19 | `github_releases` | `external` | `external` | 8119 | `mcp-github-releases` | `public_external` | `sre-platform-team` | OSS公開リリースノート・変更履歴取得 / Public OSS repository release notes lookup |
| 20 | `market_data` | `external` | `external` | 8120 | `mcp-market-data` | `public_external` | `finance-domain-team` | 為替（USD/JPY）・燃料・海上運賃指数参照 / FX, commodity & container freight index lookup |
| 21 | `weather_marine` | `external` | `external` | 8121 | `mcp-weather-marine` | `public_external` | `maritime-domain-team` | 主要港湾の風速・波浪・気象警報参照 / Marine weather, wind speed & port advisory lookup |
| 22 | `regulatory_jp` | `external` | `external` | 8122 | `mcp-regulatory-jp` | `public_external` | `legal-compliance-team` | 日本の公開法令（36協定・改善基準告示・薬機法GDP）参照 / Public Japanese regulatory lookup |

## 2. Running MCP Servers Locally (Docker Compose Profiles vs. Stdio Mode)

### Option A: Docker Compose Profiles (`core`, `domain`, `external`, `all`)
```bash
# Start only the 5 core MCP servers (knowledge_base, sql_readonly, departments, decision_history, memory)
make mcp-up PROFILE=core

# Start domain planning & ML servers
make mcp-up PROFILE=domain

# Start external intelligence servers
make mcp-up PROFILE=external
```

### Option B: Direct Local Stdio Development (No Docker Required)
Every MCP server supports `--transport stdio` for fast local debugging and `MultiServerMCPClient` stdio subprocess attachment:
```bash
PYTHONPATH="apps/api/src:." uv run python -m alba_one.mcp_servers.knowledge_base.server --transport stdio
PYTHONPATH="apps/api/src:." uv run python -m alba_one.mcp_servers.web_search.server --transport stdio
```
