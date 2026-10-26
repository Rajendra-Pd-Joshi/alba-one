"""Add `redteam_runs` and `redteam_results` tables (`alembic/versions/0003_redteam_runs_and_results.py`)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_redteam_runs_and_results"
down_revision = "0002_observability_spans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redteam_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("triggered_by", sa.String(length=128), nullable=False),
        sa.Column("trigger_kind", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("verified_environment", sa.String(length=32), nullable=False),
        sa.Column("app_version", sa.String(length=32), nullable=False),
        sa.Column("scenario_set_hash", sa.String(length=64), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("scorer_version", sa.String(length=32), nullable=False),
        sa.Column("repeats", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("critical_bypass_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("false_positive_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("budget_used_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("breakglass_ticket_id", sa.String(length=64), nullable=True),
        sa.Column("breakglass_approved_by", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_redteam_runs_version_started", "redteam_runs", ["app_version", "started_at"])
    op.create_index("ix_redteam_runs_hashes", "redteam_runs", ["scenario_set_hash", "dataset_hash", "scorer_version"])

    op.create_table(
        "redteam_results",
        sa.Column("result_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("redteam_runs.run_id"), nullable=False, index=True),
        sa.Column("scenario_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("repeat_index", sa.Integer(), nullable=False),
        sa.Column("critical_bypass", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("blocking_layer", sa.String(length=32), nullable=True),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("redteam_results")
    op.drop_index("ix_redteam_runs_hashes", table_name="redteam_runs")
    op.drop_index("ix_redteam_runs_version_started", table_name="redteam_runs")
    op.drop_table("redteam_runs")
