"""Brave Web Search Provider (`mcp_servers/web_search/providers/brave.py`).

Verified against Brave Search REST API (`GET https://api.search.brave.com/res/v1/web/search`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from alba_one.mcp_servers.web_search.providers.base import SearchResult, WebSearchProviderPort


class BraveSearchProvider(WebSearchProviderPort):
    """Calls `GET https://api.search.brave.com/res/v1/web/search` (`WEB_SEARCH_PROVIDER=brave`)."""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.search.brave.com/res/v1/web/search",
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
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params: dict[str, Any] = {
            "q": query,
            "count": max_results,
            "search_lang": "jp" if lang == "ja" else "en",
        }
        if recency_days is not None:
            if recency_days <= 1:
                params["freshness"] = "pd"
            elif recency_days <= 7:
                params["freshness"] = "pw"
            elif recency_days <= 31:
                params["freshness"] = "pm"
            else:
                params["freshness"] = "py"

        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_after = self._client is None
        try:
            resp = client.get(self.endpoint, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if close_after:
                client.close()

        now_iso = datetime.now(timezone.utc).isoformat()
        web_items = data.get("web", {}).get("results", [])
        results: list[SearchResult] = []
        for item in web_items[:max_results]:
            url = str(item.get("url", ""))
            domain = urlparse(url).hostname or "unknown"
            results.append(
                SearchResult(
                    title=str(item.get("title") or url),
                    snippet=str(item.get("description") or ""),
                    url=url,
                    published_at=item.get("age") or item.get("page_age"),
                    source_domain=domain,
                    retrieved_at=now_iso,
                    provider="brave",
                    external=True,
                )
            )
        return results
