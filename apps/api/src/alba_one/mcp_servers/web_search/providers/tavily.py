"""Tavily Web Search Provider (`mcp_servers/web_search/providers/tavily.py`).

Verified against Tavily Search REST API (`POST https://api.tavily.com/search`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from alba_one.mcp_servers.web_search.providers.base import SearchResult, WebSearchProviderPort


class TavilySearchProvider(WebSearchProviderPort):
    """Calls `POST https://api.tavily.com/search` (`WEB_SEARCH_PROVIDER=tavily`, default)."""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.tavily.com/search",
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._client = http_client

    def search(
        self,
        query: str,
        lang: str = "ja",
        max_results: int = 5,
        recency_days: int | None = 30,
    ) -> list[SearchResult]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
        }
        if recency_days is not None and recency_days > 0:
            payload["days"] = recency_days

        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_after = self._client is None
        try:
            resp = client.post(self.endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if close_after:
                client.close()

        now_iso = datetime.now(timezone.utc).isoformat()
        results: list[SearchResult] = []
        for item in data.get("results", [])[:max_results]:
            url = str(item.get("url", ""))
            domain = urlparse(url).hostname or "unknown"
            results.append(
                SearchResult(
                    title=str(item.get("title") or url),
                    snippet=str(item.get("content") or item.get("snippet") or ""),
                    url=url,
                    published_at=item.get("published_date"),
                    source_domain=domain,
                    retrieved_at=now_iso,
                    provider="tavily",
                    external=True,
                )
            )
        return results
