"""Pydantic v2 input/output schemas for the `memory` FastMCP server (`mcp_servers/memory/schemas.py`)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alba_one.memory.long_term import MemoryTypeLiteral


class SearchMemoriesInput(BaseModel):
    """Input schema for `search_memories`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    team_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=25)


class ListMyMemoriesInput(BaseModel):
    """Input schema for `list_my_memories`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    team_id: str | None = None


class DeleteMemoryInput(BaseModel):
    """Input schema for user-initiated `delete_memory`."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    memory_id: str = Field(..., min_length=1)


class ProposeMemoryInput(BaseModel):
    """Input schema for `propose_memory` (enforces `MemoryService` write policy)."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    memory_type: MemoryTypeLiteral
    topic_key: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    lang: Literal["ja", "en"] = "ja"
    team_id: str | None = None
    approval_id: str | None = None
    user_confirmed: bool = False


class MemoryRecordOutput(BaseModel):
    """Serialized long-term memory record."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    tenant_id: str
    user_id: str
    team_id: str | None = None
    memory_type: str
    topic_key: str
    content: str
    lang: str
    approval_id: str | None = None
    user_confirmed: bool
