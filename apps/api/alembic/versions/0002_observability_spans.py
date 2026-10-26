"""Add unified `spans` and `decision_run_metrics` tables (`alembic/versions/0002_observability_spans.py`)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_observability_spans"
down_revision = "0001_initial_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spans",
        sa.Column("span_id", sa.String(length=64), primary_key=True),
        sa.Column("parent_span_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("phase_step", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("model_or_tool", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("guardrail_version", sa.String(length=32), nullable=True),
        sa.Column("model_config_version", sa.String(length=32), nullable=True),
        sa.Column("tool_def_hash", sa.String(length=64), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("ttfb_ms", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cost_amount", sa.Float(), nullable=True),
        sa.Column("cost_currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("price_table_version", sa.String(length=32), nullable=False),
        sa.Column("cost_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("output_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_spans_tenant_started_at", "spans", ["tenant_id", "started_at"])
    op.create_index("ix_spans_decision_id", "spans", ["decision_id"])
    op.create_index("ix_spans_phase_step_started_at", "spans", ["phase_step", "started_at"])

    op.create_table(
        "decision_run_metrics",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
        sa.Column("per_stage_latency_json", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=True),
        sa.Column("total_cost_jpy", sa.Float(), nullable=True),
        sa.Column("unpriced_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guardrail_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit_ratio", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("budget_exhausted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("decision_run_metrics")
    op.drop_index("ix_spans_phase_step_started_at", table_name="spans")
    op.drop_index("ix_spans_decision_id", table_name="spans")
    op.drop_index("ix_spans_tenant_started_at", table_name="spans")
    op.drop_table("spans")
