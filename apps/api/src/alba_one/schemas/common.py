"""Core context, retrieval, and evidence schemas (Pydantic v2).

Every user-facing or persisted model carries `tenant_id` for strict multi-tenant
isolation (Principle 8) and `lang` for bilingual operation (Principle 7).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Language(StrEnum):
    """Supported UI and agent languages."""

    JA = "ja"
    EN = "en"


class UserRole(StrEnum):
    """RBAC roles enforced across endpoints and approvals."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    KNOWLEDGE_STEWARD = "knowledge_steward"
    APPROVER = "approver"
    ADMIN = "admin"


class EvidenceKind(StrEnum):
    """Provenance category for a cited piece of evidence."""

    KB = "kb"
    TOOL = "tool"
    WEB = "web"


class TenantContext(BaseModel):
    """Immutable tenant boundary attached to every request, query, and trace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(..., min_length=1, max_length=128, description="Unique tenant identifier")
    tenant_name: str = Field(default="ALBA Demo Corp", description="Display name of the tenant")
    isms_enforced: bool = Field(default=True, description="Whether strict ISMS audit controls are active")


class UserContext(BaseModel):
    """Authenticated user identity, role, language preference, and ACL permissions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str = Field(..., min_length=1, max_length=128)
    role: UserRole = Field(default=UserRole.ANALYST)
    language: Language = Field(default=Language.JA)
    permissions: list[str] = Field(default_factory=list)
    department: str | None = Field(default=None)
    mfa_verified: bool = Field(default=False)


class ClarificationQuestion(BaseModel):
    """Ambiguity resolution question asked before retrieval/hypothesis generation."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, description="Question presented in user's language")
    options: list[str] = Field(default_factory=list, description="Concrete suggested choices")
    required: bool = Field(default=True)
    lang: Language = Field(default=Language.JA)


class ClarificationAnswer(BaseModel):
    """User's response to a clarification question."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., min_length=1)
    answer_text: str = Field(..., min_length=1)
    lang: Language = Field(default=Language.JA)


class RewrittenQueries(BaseModel):
    """Cross-lingual (JP + EN) and domain-expanded search queries produced by query_rewriter."""

    model_config = ConfigDict(extra="forbid")

    original_query: str = Field(..., min_length=1)
    ja_queries: list[str] = Field(default_factory=list)
    en_queries: list[str] = Field(default_factory=list)
    entity_filters: list[str] = Field(default_factory=list)
    lang: Language = Field(default=Language.JA)


class RetrievedChunk(BaseModel):
    """A knowledge base chunk retrieved from hybrid (Pinecone + Postgres FTS) search."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    score: float = Field(..., ge=0.0, le=1.0)
    source_table: str = Field(..., min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    acl_tags: list[str] = Field(default_factory=list)
    lang: Language = Field(default=Language.JA)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Citation grounding a hypothesis or decision claim (Principle 3: Evidence-first)."""

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    ref_id: str = Field(
        ...,
        min_length=1,
        description="KB chunk_id, tool_call_id, or canonical web identifier",
    )
    quote_span: str = Field(..., min_length=1, description="Verbatim supporting excerpt")
    url: HttpUrl | None = Field(default=None, description="Verified source URL when kind=='web' or linked")
    lang: Language = Field(default=Language.JA)


class ToolCallRecord(BaseModel):
    """Audit record of an MCP tool invocation."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    decision_id: str | None = Field(default=None)
    mcp_server: str = Field(..., min_length=1, description="Name of the FastMCP server")
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = Field(default="")
    side_effecting: bool = Field(default=False)
    requires_approval: bool = Field(default=False)
    latency_ms: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lang: Language = Field(default=Language.JA)
