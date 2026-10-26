"""Unified MCP tool handler registry & runtime dispatcher (`mcp_servers/handlers.py`)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
import json
from typing import Any

from alba_one.kb.indexer import find_repo_root
from alba_one.mcp_servers.base import MCPServerAuditRuntime
from alba_one.mcp_servers.calculator_handlers import CALCULATOR_TOOL_HANDLERS
from alba_one.mcp_servers.domain_handlers import DOMAIN_TOOL_HANDLERS, _mem
from alba_one.mcp_servers.web_search.fetcher import fetch_page_safely

_RUNTIMES: dict[str, MCPServerAuditRuntime] = {}


def get_server_runtime(server_name: str) -> MCPServerAuditRuntime:
    """Return or create the `MCPServerAuditRuntime` singleton for `server_name`."""
    if server_name not in _RUNTIMES:
        _RUNTIMES[server_name] = MCPServerAuditRuntime(server_name)
    return _RUNTIMES[server_name]


def handle_memory_search(args: dict[str, Any]) -> dict[str, Any]:
    items = _mem().search_memories(
        tenant_id=str(args["tenant_id"]),
        user_id=str(args["user_id"]),
        query=str(args["query"]),
        team_id=args.get("team_id"),
        top_k=int(args.get("top_k", 5)),
    )
    return {"items": [asdict(m) for m in items]}


def handle_memory_list(args: dict[str, Any]) -> dict[str, Any]:
    items = _mem().list_my_memories(
        tenant_id=str(args["tenant_id"]),
        user_id=str(args["user_id"]),
        team_id=args.get("team_id"),
    )
    return {"items": [asdict(m) for m in items]}


def handle_memory_delete(args: dict[str, Any]) -> dict[str, Any]:
    deleted = _mem().delete_memory(
        tenant_id=str(args["tenant_id"]),
        user_id=str(args["user_id"]),
        memory_id=str(args["memory_id"]),
    )
    return {"deleted": deleted, "memory_id": str(args["memory_id"])}


def handle_memory_propose(args: dict[str, Any]) -> dict[str, Any]:
    item = _mem().propose_memory(
        tenant_id=str(args["tenant_id"]),
        user_id=str(args["user_id"]),
        memory_type=str(args.get("memory_type", "approved_decision_fact")),
        topic_key=str(args.get("topic_key", "general")),
        content=str(args["content"]),
        lang=str(args.get("lang", "ja")),
        team_id=args.get("team_id"),
        approval_id=args.get("approval_id"),
        user_confirmed=bool(args.get("user_confirmed", False)),
    )
    return asdict(item)


def handle_delivery_planning(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "route_code": str(args.get("route_code", "RTE-TYO-NGO-01")),
        "cold_chain_2_to_8c_available": True,
        "estimated_transit_hours": 5.5,
        "sla_compliant": True,
        "recommended_backup_route": "RTE-YOK-NGO-02",
    }


def handle_staffing(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "port_code": str(args.get("port_code", "TYO")),
        "certified_cold_chain_operators_on_shift": 6,
        "article36_overtime_remaining_hours": 6.5,
        "article36_compliant": True,
    }


def handle_vessel_allocation(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "vessel_code": str(args.get("vessel_code", "VSL-SAKURA-01")),
        "assigned_berth": "TYO-B3",
        "max_draft_meters": 14.5,
        "vessel_draft_meters": 12.8,
        "priority_cargo": "Pharma Cold-Chain Reefer (2-8C)",
    }


def handle_document_extraction(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "uri": str(args["uri"]),
        "format": str(args.get("format_hint", "pdf")),
        "extracted_text": "医薬品定温輸送SOP：2〜8℃逸脱時は30分以内に品質保証責任者へエスカレーションすること。",
        "tables_extracted": 1,
    }


def handle_deployment_status(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "environment": str(args["environment"]),
        "active_model_version": "ALBA-NEPTUNE-V2.3",
        "canary_model_version": "ALBA-NEPTUNE-V2.4",
        "canary_traffic_pct": 10,
        "healthy": True,
    }


def handle_web_search(args: dict[str, Any]) -> dict[str, Any]:
    lang = "ja" if str(args.get("lang", "ja")) == "ja" else "en"
    max_results = max(1, int(args.get("max_results", 5)))
    path = find_repo_root() / "goldens" / "fixtures" / "web_search" / f"{lang}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"query": str(args["query"]), "provider": str(args.get("provider", "fake")), "external": True, "results": raw[:max_results]}


def handle_fetch_page(args: dict[str, Any]) -> dict[str, Any]:
    url = str(args["url"])
    if args.get("offline_fixture", True):
        return {
            "source_url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "external": True,
            "text": f"Public external reference page content from {url} (SSRF-verified).",
            "guardrail_events": [],
        }
    return fetch_page_safely(url, lang=str(args.get("lang", "ja")))


def handle_news_search(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": str(args["query"]),
        "external": True,
        "articles": [
            {
                "title": "国内主要港における定温リーファー電源設備の増強計画（2026年秋）",
                "source_url": "https://maritime-news.example.com/2026/10/reefer-capacity",
                "retrieved_at": "2026-10-24T05:30:00Z",
                "external": True,
            }
        ],
    }


def handle_competitor_intel(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": str(args["query"]),
        "external": True,
        "findings": [
            {
                "competitor": "Public Maritime AI Routing Suite",
                "summary": "Public release notes highlight vessel ETA prediction; no cold-chain GDP signoff workflow.",
                "source_url": "https://maritime-news.example.com/competitor-releases/2026-q3",
                "retrieved_at": "2026-10-24T05:00:00Z",
                "external": True,
            }
        ],
    }


def handle_model_benchmarks(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": str(args["query"]),
        "external": True,
        "benchmarks": [
            {
                "benchmark_name": "JMMLU / Japanese Business Reasoning Public Leaderboard",
                "score": 0.865,
                "evaluation_caveats": (
                    "WARNING: Public leaderboard uses zero-shot general prompts without tenant ontology or "
                    "retrieval grounding; do not compare directly to internal ALBA benchmark scores."
                ),
                "source_url": "https://huggingface.co/spaces/llm-jp/leaderboard",
                "retrieved_at": "2026-10-24T04:00:00Z",
                "external": True,
            }
        ],
    }


def handle_papers(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": str(args["query"]),
        "external": True,
        "papers": [
            {
                "title": "Corrective Retrieval Augmented Generation for High-Stakes Enterprise Decision Support",
                "source_url": "https://arxiv.org/abs/2401.15884",
                "retrieved_at": "2026-10-24T03:00:00Z",
                "external": True,
            }
        ],
    }


def handle_github_releases(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args["repo"])
    return {
        "repo": repo,
        "external": True,
        "releases": [
            {
                "tag_name": "v0.3.14",
                "source_url": f"https://github.com/{repo}/releases/tag/v0.3.14",
                "retrieved_at": "2026-10-24T02:00:00Z",
                "external": True,
            }
        ],
    }


def handle_market_data(args: dict[str, Any]) -> dict[str, Any]:
    idx = str(args["index_code"]).upper()
    values = {"USDJPY": 151.45, "VLSFO_BUNKER_TON_USD": 612.0, "SCFI_FREIGHT_INDEX": 2145.8}
    return {"index_code": idx, "value": values.get(idx, 100.0), "retrieved_at": "2026-10-24T06:00:00Z", "external": True}


def handle_weather_marine(args: dict[str, Any]) -> dict[str, Any]:
    port = str(args["port_code"]).upper()
    return {
        "port_code": port,
        "gust_wind_speed_ms": 13.8 if port == "YOK" else 9.2,
        "crane_suspension_threshold_ms": 15.0,
        "advisory": "Strong breeze advisory; below 15 m/s suspension threshold." if port == "YOK" else "Normal operations.",
        "source_url": "https://www.jma.go.jp/bosai/warning/",
        "retrieved_at": "2026-10-24T06:00:00Z",
        "external": True,
    }


def handle_regulatory_jp(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": str(args["topic"]),
        "regulation_title": "労働基準法第36条（時間外・休日労働協定）およびトラック運転者の改善基準告示（2024年改正）",
        "summary": "原則月45時間・年360時間上限。医薬品GDPガイドラインにより2〜8℃定温輸送の温度記録保持が義務付けられる。",
        "source_url": "https://elaws.e-gov.go.jp/document?lawid=322AC0000000049",
        "retrieved_at": "2026-10-24T01:00:00Z",
        "external": True,
    }


ALL_TOOL_HANDLERS: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {
    **DOMAIN_TOOL_HANDLERS,
    **CALCULATOR_TOOL_HANDLERS,
    ("memory", "search_memories"): handle_memory_search,
    ("memory", "list_my_memories"): handle_memory_list,
    ("memory", "delete_memory"): handle_memory_delete,
    ("memory", "propose_memory"): handle_memory_propose,
    ("delivery_planning", "analyze_delivery_routes"): handle_delivery_planning,
    ("staffing", "analyze_staff_shifts"): handle_staffing,
    ("vessel_allocation", "analyze_berth_allocation"): handle_vessel_allocation,
    ("document_extraction", "extract_onprem_document"): handle_document_extraction,
    ("deployment_status", "get_environment_status"): handle_deployment_status,
    ("web_search", "search_web"): handle_web_search,
    ("web_search", "fetch_page"): handle_fetch_page,
    ("news_search", "search_news"): handle_news_search,
    ("competitor_intel", "track_competitor_releases"): handle_competitor_intel,
    ("model_benchmarks", "lookup_public_benchmarks"): handle_model_benchmarks,
    ("papers", "search_papers"): handle_papers,
    ("github_releases", "list_repo_releases"): handle_github_releases,
    ("market_data", "get_market_indices"): handle_market_data,
    ("weather_marine", "get_port_weather"): handle_weather_marine,
    ("regulatory_jp", "lookup_jp_regulation"): handle_regulatory_jp,
}


def invoke_mcp_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    bearer_token: str | None = "dev-mcp-token",
    approval_id: str | None = None,
    user_confirmed: bool = False,
    outbound_query_policy: str = "generalize",
    simulated_latency_ms: float = 0.0,
) -> dict[str, Any]:
    """Execute `(server_name, tool_name)` through `MCPServerAuditRuntime` with full guardrails and logging."""
    rt = get_server_runtime(server_name)
    handler = ALL_TOOL_HANDLERS.get((server_name, tool_name), lambda a: a)
    return rt.invoke_guarded(
        tool_name,
        arguments,
        handler,
        bearer_token=bearer_token,
        approval_id=approval_id,
        user_confirmed=user_confirmed,
        outbound_query_policy=outbound_query_policy,
        simulated_latency_ms=simulated_latency_ms,
    )
