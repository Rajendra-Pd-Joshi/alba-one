#!/usr/bin/env bash
# ==============================================================================
# ALBA ONE — Local Verification Script (scripts/verify_local.sh)
# Executes:
#   1. Environment & lockfile sync (`uv lock` / `uv sync`)
#   2. Stdlib pure-logic unit & contract tests (`unittest`)
#   3. Full pytest suite (`pytest`, including fakeredis & Pydantic v2 tests)
#   4. Phase 2 KB Indexer CLI & Chunking Comparison Eval
#   5. Phase 3 Retrieval Pipeline CLI & Retriever Ablation Eval (`--compare`)
#   6. Phase 4 7-Layer Guardrail Demo & Bedrock Guardrail Provisioner (`--dry-run`)
#   7. Phase 5 MCP Client Tool Discovery, 22-Server Contract Tests & MCP Evals
#   8. Phase 6 Hypothesis Generator CLI (JP & EN) & Hypothesis Eval (`--allow-draft`)
#   9. Phase 7 Decision Judge, HITL Outbox, Outcomes & E2E Evals (`--allow-draft`)
#  10. Phase 8 Frontend Brand Token Check & Production Mock-Ban Guard
#  11. Phase 9 & 11 Ops Evals, Cost Recompute, Safety Evals & 11-Family Red-Team Suite
#  12. Phase 10 Container Hardening Audit (`ci/scripts/check_images.sh`) & Web Startup Check
#  13. Ruff linter, Mypy strict type check, and Docker Compose config check
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> [1/13] Checking .env file..."
if [ ! -f .env ]; then
  echo "    .env not found; copying from .env.example for local verification..."
  cp .env.example .env
fi

echo "==> [2/13] Syncing Python 3.12 environment via uv..."
uv lock
uv sync --all-packages --extra dev

echo "==> [3/13] Running stdlib pure-logic unit & contract tests..."
PYTHONPATH="apps/api/src:." uv run python -m unittest discover -s apps/api/tests/unit -p "test_*.py" -v

echo "==> [4/13] Running full pytest suite (Pydantic v2 + fakeredis + FastAPI + 22 MCP Contracts)..."
uv run pytest apps/api/tests/unit apps/api/tests/mcp -v

echo "==> [5/13] Running Phase 2 & Phase 3 CLIs and Smoke Evals..."
PYTHONPATH="apps/api/src:." uv run python -m alba_one.kb.indexer --tenant demo --full > /dev/null
PYTHONPATH="apps/api/src:." uv run python -m evals.chunking_compare --dataset goldens/chunking_smoke.json --allow-draft --out evals/reports
PYTHONPATH="apps/api/src:." uv run python -m alba_one.retrieval.pipeline "東京大井ふ頭から横浜本牧への配送ルートRT-KNT-101の割当車両とSLA時間は？" --lang ja --non-interactive > /dev/null
PYTHONPATH="apps/api/src:." uv run python -m evals.retriever_eval --dataset goldens/retriever.json --allow-draft --compare --out evals/reports

echo "==> [6/13] Running Phase 4 Guardrail Acceptance Demo & Bedrock IaC Dry-Run..."
PYTHONPATH="apps/api/src:." uv run python infra/bedrock/create_guardrail.py --dry-run --tier STANDARD --cross-region-profile apac.guardrail.v1:0 > /dev/null
PYTHONPATH="apps/api/src:." uv run python -m alba_one.guardrails.pipeline > /dev/null

echo "==> [7/13] Running Phase 5 MCP Client Tool Discovery & 22-Server MCP Evaluations..."
PYTHONPATH="apps/api/src:." uv run python -m alba_one.mcp_client.client --list-tools > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/mcp/run_all.py --allow-draft > /dev/null

echo "==> [8/13] Running Phase 6 Hypothesis Generator CLI (JP & EN) & Hypothesis Eval..."
PYTHONPATH="apps/api/src:." uv run python -m alba_one.agents.hypothesis.graph "Should we release model v2.4 to production?" --lang en > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/hypothesis_eval.py --allow-draft > /dev/null

echo "==> [9/13] Running Phase 7 Decision Judge, End-to-End, and Calibration Evals..."
PYTHONPATH="apps/api/src:." uv run python evals/judge_eval.py --allow-draft > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/end_to_end_eval.py --allow-draft > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/calibration_eval.py --synthetic-demo > /dev/null

echo "==> [10/13] Running Phase 8 Frontend Production Mock Guard..."
NODE_ENV=production NEXT_PUBLIC_USE_MOCKS=false node apps/web/scripts/assert-no-mocks-in-prod.mjs

echo "==> [11/13] Running Phase 9 & 11 Cost Recompute, Ops Evals, Safety Eval & Red-Team Suite..."
PYTHONPATH="apps/api/src:." uv run python scripts/recompute_costs.py --dry-run > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/ops_latency_eval.py > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/ops_cost_eval.py > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/ops_reliability_eval.py > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/safety_guardrails_eval.py --allow-draft > /dev/null
PYTHONPATH="apps/api/src:." uv run python evals/red_team.py --repeats 3

echo "==> [12/13] Running Phase 10 Container Hardening Audit & Web Startup Fail-Closed Check..."
bash ci/scripts/check_images.sh
APP_ENV=production NEXT_PUBLIC_USE_MOCKS=false node apps/web/scripts/check-startup.mjs

echo "==> [13/13] Running Ruff, Mypy, and Docker Compose validation..."
uv run ruff check .
uv run mypy apps/api/src
docker compose -f infra/docker-compose.yml config > /dev/null
docker compose -f infra/docker-compose.prod-like.yml config > /dev/null
echo "    infra/docker-compose.yml and infra/docker-compose.prod-like.yml are valid."

echo "✅ All ALBA ONE Phase 1–11 checks passed!"
