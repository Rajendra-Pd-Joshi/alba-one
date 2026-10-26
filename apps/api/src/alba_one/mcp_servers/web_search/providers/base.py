"""Pluggable Web Search Provider interface & Pydantic v2 model (`mcp_servers/web_search/providers/base.py`)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class SearchResult(BaseModel):
    """Canonical external web search result returned by all search providers."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    snippet: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    published_at: str | None = Field(default=None)
    source_domain: str = Field(..., min_length=1)
    retrieved_at: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    external: bool = Field(default=True)


@runtime_checkable
class WebSearchProviderPort(Protocol):
    """Protocol implemented by `tavily`, `brave`, `firecrawl`, and `fake` providers."""

    def search(
        self,
        query: str,
        lang: str = "ja",
        max_results: int = 5,
        recency_days: int | None = 30,
    ) -> list[SearchResult]: ...
