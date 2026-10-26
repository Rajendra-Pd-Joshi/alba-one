"""Stage 3: Adaptive RAG Router (`retrieval/router.py`).

Classifies a query into one of 4 routing strategies:
- `no_retrieval`: Pure conversational greeting or meta-question about the UI.
- `single_hop`: Direct lookup of a single entity, route, vessel, staff member, or model version.
- `multi_hop`: Decision question comparing multiple options or combining constraints across tables
  (e.g., vessel berth + route vehicle + staff overtime).
- `needs_external`: Query explicitly asking for external competitor, market, weather, or public leaderboard facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RouteClassification = Literal["no_retrieval", "single_hop", "multi_hop", "needs_external"]

_GREETING_MARKERS: tuple[str, ...] = (
    "こんにちは",
    "おはよう",
    "ありがとう",
    "hello",
    "hi there",
    "thank you",
)

_EXTERNAL_MARKERS: tuple[str, ...] = (
    "競合他社",
    "市場価格",
    "外部ニュース",
    "公開リーダーボード",
    "気象庁",
    "competitor",
    "public leaderboard",
    "market index",
    "breaking news",
    "arxiv",
)

_MULTI_HOP_MARKERS: tuple[str, ...] = (
    "比較",
    "優先順位",
    "案a",
    "案b",
    "と",
    "および",
    "両方",
    "判断",
    "compare",
    "versus",
    "vs",
    "both",
    "should we",
    "trade-off",
    "allocate",
)


@dataclass(frozen=True)
class AdaptiveRouteDecision:
    """Output of the Adaptive RAG router."""

    classification: RouteClassification
    strategy_description: str
    top_k_per_query: int
    use_multi_query: bool
    prefer_external_if_low_recall: bool


def route_query(query: str) -> AdaptiveRouteDecision:
    """Classify `query` and select the appropriate Adaptive RAG retrieval parameters."""
    cleaned = query.strip().lower()
    if not cleaned or (len(cleaned) <= 12 and any(g in cleaned for g in _GREETING_MARKERS)):
        return AdaptiveRouteDecision(
            classification="no_retrieval",
            strategy_description="Skip KB lookup for conversational greeting",
            top_k_per_query=0,
            use_multi_query=False,
            prefer_external_if_low_recall=False,
        )

    if any(ext in cleaned for ext in _EXTERNAL_MARKERS):
        return AdaptiveRouteDecision(
            classification="needs_external",
            strategy_description="Run hybrid internal KB search + allow external search fallback",
            top_k_per_query=6,
            use_multi_query=True,
            prefer_external_if_low_recall=True,
        )

    if any(mh in cleaned for mh in _MULTI_HOP_MARKERS) or len(cleaned) > 45:
        return AdaptiveRouteDecision(
            classification="multi_hop",
            strategy_description="Multi-query hybrid retrieval across multiple entity types with RRF",
            top_k_per_query=6,
            use_multi_query=True,
            prefer_external_if_low_recall=False,
        )

    return AdaptiveRouteDecision(
        classification="single_hop",
        strategy_description="Direct single-hop hybrid retrieval with parent-child context expansion",
        top_k_per_query=4,
        use_multi_query=False,
        prefer_external_if_low_recall=False,
    )
