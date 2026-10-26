# ADR 0004: Unified `spans` Table & `decision_run_metrics` in PostgreSQL

- **Status**: Accepted
- **Date**: 2026-10-24
- **Owners**: Observability & Core Platform Team

## Context
In Phase 9, every LLM call, embedding call, rerank call, guardrail check, MCP tool call, and deterministic calculator call must emit a structured telemetry span so that:
1. PostgreSQL serves as the authoritative system of record for operational metrics (latency `p50/p95/p99` via `percentile_cont`, token usage, cost in USD/JPY, retries, cache hit rates, and unpriced call counts).
2. The Quality & Guardrails UI (`/api/v1/metrics/...`) and offline ops evaluations (`evals/ops_*_eval.py`) work identically even when LangSmith is unreachable or disabled.

We evaluated two options:
- **Option A**: Extend `llm_calls` and `tool_calls` separately and `UNION ALL` them at query time across 6 call kinds (`llm | embedding | rerank | guardrail | mcp_tool | calc`).
- **Option B (Chosen)**: Add a single unified `spans` table alongside a `decision_run_metrics` per-run summary table (while keeping `llm_calls` and `tool_calls` for backward-compatible audit queries).

## Decision
We choose **Option B (Unified `spans` table + `decision_run_metrics` summary table)**:
1. **Single-Table `percentile_cont` Queries**: Computing exact `percentile_cont(0.50 | 0.95 | 0.99) WITHIN GROUP (ORDER BY latency_ms)` grouped by `phase_step` (`clarify`, `rewrite`, `retrieve`, `rerank`, `embed`, `input_guardrail`, `retriever_guardrail`, `plan`, `tool_call`, `hypothesis`, `confidence`, `judge`, `output_guardrail`, `memory`, `approval_resume`, `writeback`), `model_or_tool`, or `tenant_id` uses a single indexed B-tree scan without runtime `UNION ALL` overhead.
2. **Indexes**:
   - `ix_spans_tenant_started_at` on `(tenant_id, started_at)`
   - `ix_spans_decision_id` on `(decision_id)`
   - `ix_spans_phase_step_started_at` on `(phase_step, started_at)`
3. **Retention & Partitioning (`TODO(owner)`)**:
   - `spans` is designed for monthly range partitioning on `started_at` (`PARTITION BY RANGE (started_at)` in production Postgres).
   - Default hot retention window is `TODO(owner): confirm 90-day vs 365-day span retention under ISMS policy before archiving to cold storage`.
