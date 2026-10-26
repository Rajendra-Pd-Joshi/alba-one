"""# STUB: Placeholder external search adapter for Phase 3 (`retrieval/external_stub.py`).

Tracked in `docs/STUBS.md`:
"replace with MCP-client-backed adapter in Phase 5 (web_search, news_search servers)".
"""

from __future__ import annotations

import logging

from alba_one.retrieval.ports import ExternalResult, ExternalSearchPort

logger = logging.getLogger("alba_one.retrieval.external_stub")


class StubExternalSearchAdapter(ExternalSearchPort):
    """# STUB: Returns an empty list and logs that real external MCP search is wired in Phase 5."""

    def search(self, query: str, lang: str, max_results: int = 3) -> list[ExternalResult]:
        """# STUB: Log invocation and return `[]` until Phase 5 MCP servers are wired."""
        logger.warning(
            "StubExternalSearchAdapter called (no real external search wired yet; replace in Phase 5)",
            extra={
                "structured_data": {
                    "query": query,
                    "lang": lang,
                    "max_results": max_results,
                    "stub": True,
                }
            },
        )
        return []
