# ALBA ONE — Operational Runbook (`docs/RUNBOOK.md`)

## 1. Prerequisites (Developer Desktop)
- **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Docker Desktop** or **Docker Engine + Docker Compose v2**

## 2. First-Time Setup & Verification

From the `alba-one/` repository root:

```bash
# 1. Copy the bilingual environment file and review variables
cp .env.example .env

# 2. Generate uv.lock and install Python 3.12 workspace + dev dependencies
uv lock
uv sync --all-packages --extra dev

# 3. Run the full local verification script (unit tests, ruff, mypy, docker compose config)
./scripts/verify_local.sh
```

## 3. Starting the Stack with Docker Compose

```bash
# Bring up PostgreSQL 16 (auto-seeds infra/seed/01_synthetic_demo_company.sql), Redis 7.4, and FastAPI
docker compose -f infra/docker-compose.yml up --build -d

# Check liveness
curl -s http://localhost:8000/health | python3 -m json.tool

# Check deep dependency status (Postgres, Redis, Pinecone, Bedrock Guardrail, configured models)
curl -s http://localhost:8000/health/deep | python3 -m json.tool
```

## 4. Running Database Migrations & Seeds Manually

```bash
cd apps/api
uv run alembic upgrade head
psql postgresql://alba:alba_dev_password@localhost:5432/alba_one -f ../../infra/seed/01_synthetic_demo_company.sql
```
