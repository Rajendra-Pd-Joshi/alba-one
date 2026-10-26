"""Deterministic Fake Web Search Provider reading `goldens/fixtures/web_search/*.json` (`providers/fake.py`).

Used in unit tests and offline MCP evaluations so no test ever calls a live external search API.
"""

from __future__ import annotations

import json
from pathlib import Path

from alba_one.kb.indexer import find_repo_root
from alba_one.mcp_servers.web_search.providers.base import SearchResult, WebSearchProviderPort


class FakeWebSearchProvider(WebSearchProviderPort):
    """Loads deterministic JP/EN search results from `goldens/fixtures/web_search/{ja,en}.json`."""

    def __init__(self, fixtures_dir: str | Path | None = None) -> None:
        if fixtures_dir is None:
            root = find_repo_root()
            self.fixtures_dir = root / "goldens" / "fixtures" / "web_search"
        else:
            self.fixtures_dir = Path(fixtures_dir)

    def search(
        self,
        query: str,
        lang: str = "ja",
        max_results: int = 5,
        recency_days: int | None = 30,
    ) -> list[SearchResult]:
        lang_file = "ja.json" if lang == "ja" else "en.json"
        path = self.fixtures_dir / lang_file
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [SearchResult(**item) for item in raw[: max(1, max_results)]]
