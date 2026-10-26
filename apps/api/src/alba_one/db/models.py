"""SQLAlchemy 2.0 ORM models for the 12 core ALBA ONE tables.

Tables:
1. tenants
2. users
3. decisions
4. hypotheses
5. tool_calls
6. approvals
7. outcomes
8. guardrail_events
9. llm_calls
10. kb_documents
11. kb_chunks
12. eval_runs
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from alba_one.db.base import Base, TenantScopedMixin


class TenantORM(Base):
    """Organization tenant registered in ALBA ONE (`tenants`)."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name_ja: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    isms_enforced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserORM(Base, TenantScopedMixin):
    """User account scoped to a tenant (`users`)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    display_name_ja: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="analyst")
    department: Mapped[str] = mapped_column(String(128), nullable=False, default="operations")
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class DecisionORM(Base, TenantScopedMixin):
    """Decision session linking query, recommendation, and current status (`decisions`)."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id"), nullable=False)
    workflow_domain: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_approval", nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    options_compared: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cited_hypothesis_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class HypothesisORM(Base, TenantScopedMixin):
    """Generated hypothesis with evidence citations and confidence breakdown (`hypotheses`)."""

    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("decisions.id"), index=True, nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    stance: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ToolCallORM(Base, TenantScopedMixin):
    """MCP tool invocation audit log (`tool_calls`)."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("decisions.id"), index=True, nullable=True
    )
    mcp_server: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    side_effecting: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class ApprovalORM(Base, TenantScopedMixin):
    """Human-in-the-loop approval or rejection record (`approvals`)."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("decisions.id"), index=True, nullable=False
    )
    approver_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    edited_conditions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class OutcomeORM(Base, TenantScopedMixin):
    """Outcome review record linking decision to measured business impact (`outcomes`)."""

    __tablename__ = "outcomes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("decisions.id"), index=True, nullable=False
    )
    measured_result: Mapped[str] = mapped_column(Text, nullable=False)
    variance_reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(128), ForeignKey("users.id"), nullable=False)
    writeback_chunk_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class GuardrailEventORM(Base, TenantScopedMixin):
    """Guardrail enforcement log across all 7 layers (`guardrail_events`)."""

    __tablename__ = "guardrail_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("decisions.id"), index=True, nullable=True
    )
    layer: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    policy: Mapped[str] = mapped_column(String(128), nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class LLMCallORM(Base, TenantScopedMixin):
    """Telemetry record for every LLM invocation (`llm_calls`)."""

    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("decisions.id"), index=True, nullable=True
    )
    model: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class KBDocumentORM(Base, TenantScopedMixin):
    """Source document or operational table record in the knowledge base (`kb_documents`)."""

    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    pillar: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_table: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    acl_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class KBChunkORM(Base, TenantScopedMixin):
    """Indexed text chunk for hybrid Postgres FTS + Pinecone retrieval (`kb_chunks`)."""

    __tablename__ = "kb_chunks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("kb_documents.id"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokenized_text: Mapped[str] = mapped_column(
        Text, default="", nullable=False, doc="Space-delimited Sudachi/MeCab tokens for JP FTS"
    )
    source_table: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    entity_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    acl_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    pinecone_vector_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class EvalRunORM(Base, TenantScopedMixin):
    """Execution record of a DeepEval / GEval benchmark run (`eval_runs`)."""

    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    eval_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    dataset_path: Mapped[str] = mapped_column(String(255), nullable=False)
    judge_model: Mapped[str] = mapped_column(String(128), nullable=False)
    main_model: Mapped[str] = mapped_column(String(128), nullable=False)
    allow_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
