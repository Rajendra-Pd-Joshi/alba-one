"""Initial foundation schema: 12 tenant-isolated tables + operational domain tables.

Revision ID: 0001_initial_foundation
Revises: None
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_Audit_columns() -> list[sa.Column[object]]:
    """Shared tenant, language, synthetic marker, and timestamp columns."""
    return [
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("lang", sa.String(8), nullable=False, server_default="ja"),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    """Create all 12 core Decision OS tables plus operational entity tables for seeding."""
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name_ja", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("isms_enforced", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("display_name_ja", sa.String(255), nullable=False),
        sa.Column("display_name_en", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="analyst"),
        sa.Column("department", sa.String(128), nullable=False, server_default="operations"),
        sa.Column("permissions", sa.JSON(), nullable=False),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "decisions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workflow_domain", sa.String(64), nullable=False, index=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
        sa.Column("verdict", sa.String(32), nullable=True),
        sa.Column("options_compared", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("cited_hypothesis_ids", sa.JSON(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=False, index=True
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("stance", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_json", sa.JSON(), nullable=False),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=True, index=True
        ),
        sa.Column("mcp_server", sa.String(64), nullable=False, index=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("side_effecting", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=False, index=True
        ),
        sa.Column("approver_id", sa.String(128), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("edited_conditions", sa.JSON(), nullable=False),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "outcomes",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=False, index=True
        ),
        sa.Column("measured_result", sa.Text(), nullable=False),
        sa.Column("variance_reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(128), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("writeback_chunk_id", sa.String(128), nullable=True),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "guardrail_events",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=True, index=True
        ),
        sa.Column("layer", sa.String(32), nullable=False, index=True),
        sa.Column("action", sa.String(32), nullable=False, index=True),
        sa.Column("policy", sa.String(128), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=True, index=True
        ),
        sa.Column("model", sa.String(128), nullable=False, index=True),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "kb_documents",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("pillar", sa.String(64), nullable=False, index=True),
        sa.Column("source_table", sa.String(128), nullable=False, index=True),
        sa.Column("entity_ids", sa.JSON(), nullable=False),
        sa.Column("acl_tags", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(128),
            sa.ForeignKey("kb_documents.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokenized_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_table", sa.String(128), nullable=False, index=True),
        sa.Column("entity_ids", sa.JSON(), nullable=False),
        sa.Column("acl_tags", sa.JSON(), nullable=False),
        sa.Column("pinecone_vector_id", sa.String(128), nullable=True),
        *_tenant_Audit_columns(),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("eval_name", sa.String(128), nullable=False, index=True),
        sa.Column("dataset_path", sa.String(255), nullable=False),
        sa.Column("judge_model", sa.String(128), nullable=False),
        sa.Column("main_model", sa.String(128), nullable=False),
        sa.Column("allow_draft", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_tenant_Audit_columns(),
    )


def downgrade() -> None:
    """Drop all 12 core tables in reverse dependency order."""
    for table in [
        "eval_runs",
        "kb_chunks",
        "kb_documents",
        "llm_calls",
        "guardrail_events",
        "outcomes",
        "approvals",
        "tool_calls",
        "hypotheses",
        "decisions",
        "users",
        "tenants",
    ]:
        op.drop_table(table)
