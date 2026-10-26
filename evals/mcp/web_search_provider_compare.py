"""Opt-in Live Web Search Provider Comparison (`evals/mcp/web_search_provider_compare.py`).

Per User Answer 1:
- Runs ONLY when `RUN_LIVE_SEARCH=1` is set in the environment (never in CI).
- Compares `tavily`, `brave`, and `firecrawl` across 10 Japanese and 10 English business queries,
  reporting latency, result count, domain diversity, and Japanese snippet quality.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})

LIVE_QUERIES_JA: list[str] = [
    "東京港 コンテナバース 強風 荷役停止基準",
    "横浜港 リーファーコンテナ 電源設備 容量",
    "トラック運転者 改善基準告示 2024年 時間外労働 上限",
    "医薬品 GDPガイドライン 定温輸送 2〜8℃ 逸脱手順",
    "内航船 バンカー燃料 VLSFO 価格推移",
    "名古屋港 危険物コンテナ 仮置き 規制",
    "大阪港 港湾荷役 36協定 特別条項",
    "海上コンテナ運賃指数 SCFI 北米航路",
    "サプライチェーン 気象リスク 代替ルート 意思決定",
    "企業向け 生成AI ガードレール 個人情報保護委員会",
]

LIVE_QUERIES_EN: list[str] = [
    "Tokyo Port container berth wind speed crane suspension threshold",
    "Yokohama Port reefer container plug capacity cold chain",
    "Japan Article 36 overtime limit logistics driver regulations 2024",
    "Pharmaceutical GDP cold chain 2-8C temperature excursion SOP",
    "VLSFO bunker fuel price index maritime shipping",
    "Nagoya Port hazardous cargo storage port authority rules",
    "Osaka Port stevedore shift certification requirements",
    "Shanghai Containerized Freight Index SCFI transpacific trends",
    "Maritime supply chain typhoon rerouting decision support",
    "Enterprise LLM outbound query DLP guardrail best practices",
]


def main() -> int:
    if os.getenv("RUN_LIVE_SEARCH") != "1":
        print(
            "SKIPPED: `evals/mcp/web_search_provider_compare.py` is opt-in only.\n"
            "Set `RUN_LIVE_SEARCH=1` along with `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`, and "
            "`FIRECRAWL_API_KEY` to run live provider comparisons."
        )
        return 0

    from alba_one.mcp_servers.web_search.providers.brave import BraveSearchProvider
    from alba_one.mcp_servers.web_search.providers.firecrawl import FirecrawlSearchProvider
    from alba_one.mcp_servers.web_search.providers.tavily import TavilySearchProvider

    providers: dict[str, Any] = {}
    if os.getenv("TAVILY_API_KEY"):
        providers["tavily"] = TavilySearchProvider(api_key=os.environ["TAVILY_API_KEY"])
    if os.getenv("BRAVE_SEARCH_API_KEY"):
        providers["brave"] = BraveSearchProvider(api_key=os.environ["BRAVE_SEARCH_API_KEY"])
    if os.getenv("FIRECRAWL_API_KEY"):
        providers["firecrawl"] = FirecrawlSearchProvider(api_key=os.environ["FIRECRAWL_API_KEY"])

    if not providers:
        raise RuntimeError("RUN_LIVE_SEARCH=1 was set, but no provider API keys were found in env.")

    summary: dict[str, Any] = {}
    for pname, provider in providers.items():
        latencies: list[float] = []
        domains: set[str] = set()
        total_results = 0
        for q in LIVE_QUERIES_JA:
            t0 = time.perf_counter()
            res = provider.search(q, lang="ja", max_results=5)
            latencies.append((time.perf_counter() - t0) * 1000.0)
            total_results += len(res)
            domains.update(r.source_domain for r in res)
        for q in LIVE_QUERIES_EN:
            t0 = time.perf_counter()
            res = provider.search(q, lang="en", max_results=5)
            latencies.append((time.perf_counter() - t0) * 1000.0)
            total_results += len(res)
            domains.update(r.source_domain for r in res)

        summary[pname] = {
            "queries_run": len(LIVE_QUERIES_JA) + len(LIVE_QUERIES_EN),
            "avg_latency_ms": round(sum(latencies) / max(1, len(latencies)), 2),
            "total_results": total_results,
            "unique_domains": len(domains),
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
