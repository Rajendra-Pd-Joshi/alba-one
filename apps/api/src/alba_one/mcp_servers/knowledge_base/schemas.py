"""Pydantic v2 input and output schemas for the `knowledge_base` FastMCP server."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KBSearchInput(BaseModel):
    """Input schema for `kb_search` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    caller_role: str = Field(default="analyst")
    query: str = Field(..., min_length=1)
    lang: str | None = Field(default=None)
    entity_type: str | None = Field(default=None)
    top_k: int = Field(default=5, ge=1, le=25)


class KBSearchHit(BaseModel):
    """Single retrieved chunk hit with text resolved from on-prem Postgres."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    tenant_id: str
    text: str
    score: float
    source_table: str
    entity_type: str
    entity_ids: list[str]
    acl_tags: list[str]
    lang: str


class KBSearchOutput(BaseModel):
    """Output schema for `kb_search` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    hits: list[KBSearchHit]


class KBGetChunkInput(BaseModel):
    """Input schema for `kb_get_chunk` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    caller_role: str = Field(default="analyst")
    chunk_id: str = Field(..., min_length=1)


class KBGetChunkOutput(BaseModel):
    """Output schema for `kb_get_chunk` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    tenant_id: str
    text: str
    source_table: str
    entity_type: str
    entity_ids: list[str]
    acl_tags: list[str]
    valid_from: str
    valid_to: str | None = None
    lang: str
    parent_chunk_id: str | None = None


class KBGetEntityInput(BaseModel):
    """Input schema for `kb_get_entity` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    caller_role: str = Field(default="analyst")
    entity_type: str = Field(..., min_length=1)


class KBEntitySummary(BaseModel):
    """Pydantic v2 summary of an ontology entity and its indexed chunk count."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str
    label_ja: str
    label_en: str
    source_view: str
    source_table: str
    primary_key: str
    acl_tags: list[str]
    attributes: list[str]
    decision_fields: dict[str, str]
    chunk_count: int = 0


class KBListEntitiesInput(BaseModel):
    """Input schema for `kb_list_entities` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    caller_role: str = Field(default="analyst")


class KBListEntitiesOutput(BaseModel):
    """Output schema for `kb_list_entities` MCP tool."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    entities: list[KBEntitySummary]
