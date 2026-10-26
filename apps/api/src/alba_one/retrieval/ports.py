"""External search port and Pydantic v2 model for Corrective RAG (`retrieval/ports.py`).

Defines `ExternalResult` and `ExternalSearchPort` (`typing.Protocol`) so that
`retrieval/corrective.py` depends only on the abstract port via dependency
injection, and Phase 5 can swap in the MCP-client-backed adapter (`web_search`,
`news_search`) without changing retrieval pipeline code.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ExternalResult(BaseModel):
    """A single external web or news search result returned by `ExternalSearchPort`.

    Every result is explicitly marked `external=True` and carries `source_url`
    and `retrieved_at` for downstream citation grounding.
    """

    text: str = Field(..., min_length=1, description="Extracted snippet or summary text")
    source_url: str = Field(..., min_length=1, description="Canonical URL of the external source")
    retrieved_at: str = Field(..., min_length=1, description="ISO-8601 timestamp of retrieval")
    source_kind: Literal["web", "news"] = Field(..., description="External source category")
    external: bool = Field(default=True, description="Always True for external fallback results")


@runtime_checkable
class ExternalSearchPort(Protocol):
    """Port interface for external search fallback in Corrective RAG."""

    def search(self, query: str, lang: str, max_results: int = 3) -> list[ExternalResult]:
        """Search external web/news sources and return `ExternalResult` items."""
        ...
