# ==============================================================================
# ALBA ONE — Root Makefile
# Usage:
#   make mcp-up PROFILE=core
#   make mcp-up PROFILE=domain
#   make mcp-up PROFILE=external
#   make mcp-up PROFILE=all
#   make mcp-down
# ==============================================================================

PROFILE ?= core
COMPOSE_FILE := infra/docker-compose.yml

.PHONY: mcp-up mcp-down lint typecheck test eval-mcp verify

mcp-up:
	docker compose -f $(COMPOSE_FILE) --profile $(PROFILE) up --build -d

mcp-down:
	docker compose -f $(COMPOSE_FILE) --profile all down

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy apps/api/src

test:
	PYTHONPATH="apps/api/src:." uv run pytest apps/api/tests -v

eval-mcp:
	PYTHONPATH="apps/api/src:." uv run python -m evals.mcp.run_all --allow-draft --out evals/reports

verify:
	./scripts/verify_local.sh
