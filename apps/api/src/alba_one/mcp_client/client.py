"""MCP Client & External Search Adapter (`mcp_client/client.py`).

Provides:
1. `build_multiserver_mcp_config()` reading `mcp_servers/registry.yaml` for `langchain-mcp-adapters` (`MultiServerMCPClient`).
2. `AGENT_TOOL_ALLOWLISTS`: per-agent server/tool allowlists so each agent only sees the tools it is allowed to call.
3. `discover_registered_tools()`: returns the complete catalogue of all 22 servers and their tools with class (`read` | `write` | `external`), profile, port, and required arguments.
4. `MCPExternalSearchAdapter`: replaces Phase 3's `ExternalSearchStub` so corrective retrieval calls the `web_search` and `news_search` MCP servers through Layer 5 tool guardrails.
5. CLI: `uv run python -m alba_one.mcp_client.client --list-tools`
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
import sys
from typing import Any

from alba_one.guardrails.tool_layer import TOOL_CATALOG
from alba_one.mcp_servers.base import MCPServerRegistryEntry, load_mcp_registry
from alba_one.mcp_servers.handlers import invoke_mcp_tool
from alba_one.retrieval.ports import ExternalResult, ExternalSearchPort

AGENT_TOOL_ALLOWLISTS: dict[str, list[str]] = {
    "retriever": [
        "knowledge_base",
        "sql_readonly",
        "decision_history",
        "memory",
        "web_search",
        "news_search",
        "regulatory_jp",
    ],
    "hypothesis_generator": [
        "knowledge_base",
        "sql_readonly",
        "departments",
        "experiment_tracking",
        "benchmark_registry",
        "decision_history",
        "delivery_planning",
        "staffing",
        "vessel_allocation",
        "document_extraction",
        "deployment_status",
        "web_search",
        "news_search",
        "competitor_intel",
        "model_benchmarks",
        "papers",
        "github_releases",
        "market_data",
        "weather_marine",
        "regulatory_jp",
    ],
    "decision_judge": [
        "knowledge_base",
        "departments",
        "approvals",
        "benchmark_registry",
        "decision_history",
        "memory",
    ],
    "outcome_reviewer": [
        "knowledge_base",
        "decision_history",
        "approvals",
        "memory",
    ],
}


def build_multiserver_mcp_config(
    *,
    profile_filter: str | None = None,
    agent_role: str | None = None,
    transport_override: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the connection dict consumed by `langchain_mcp_adapters.client.MultiServerMCPClient`."""
    registry = load_mcp_registry()
    allowed_servers = set(AGENT_TOOL_ALLOWLISTS.get(agent_role, registry.keys())) if agent_role else set(registry.keys())
    bearer = os.getenv("MCP_BEARER_TOKEN", "dev-mcp-token")

    config: dict[str, dict[str, Any]] = {}
    for name, entry in registry.items():
        if name not in allowed_servers:
            continue
        if profile_filter and profile_filter != "all" and entry.profile != profile_filter:
            continue
        transport = transport_override or entry.transport
        if transport == "stdio":
            config[name] = {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", f"alba_one.mcp_servers.{name}.server", "--transport", "stdio"],
                "env": {"MCP_BEARER_TOKEN": bearer},
            }
        else:
            host = os.getenv(f"MCP_{name.upper()}_HOST", "127.0.0.1")
            config[name] = {
                "transport": "streamable_http",
                "url": f"http://{host}:{entry.port}/mcp",
                "headers": {"Authorization": f"Bearer {bearer}"},
            }
    return config


def discover_registered_tools(
    *,
    agent_role: str | None = None,
    profile_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return all registered MCP tools across the 22 servers with their server metadata and class."""
    registry: dict[str, MCPServerRegistryEntry] = load_mcp_registry()
    allowed_servers = set(AGENT_TOOL_ALLOWLISTS.get(agent_role, registry.keys())) if agent_role else set(registry.keys())

    discovered: list[dict[str, Any]] = []
    for (server_name, tool_name), spec in TOOL_CATALOG.items():
        if server_name not in allowed_servers:
            continue
        entry = registry.get(server_name)
        if entry is None:
            continue
        if profile_filter and profile_filter != "all" and entry.profile != profile_filter:
            continue
        discovered.append(
            {
                "mcp_server": server_name,
                "tool_name": tool_name,
                "class": spec["class"],
                "profile": entry.profile,
                "transport": entry.transport,
                "port": entry.port,
                "required_args": list(spec["required_args"]),
                "owner": entry.owner,
                "data_sensitivity": entry.data_sensitivity,
                "purpose_ja": entry.purpose_ja,
                "purpose_en": entry.purpose_en,
            }
        )
    return discovered


class MCPExternalSearchAdapter(ExternalSearchPort):
    """Replaces Phase 3 `ExternalSearchStub` with guarded calls to `web_search` and `news_search` MCP servers."""

    def __init__(
        self,
        *,
        tenant_id: str = "tenant_alba_demo",
        bearer_token: str | None = None,
        outbound_query_policy: str = "generalize",
    ) -> None:
        self.tenant_id = tenant_id
        self.bearer_token = bearer_token or os.getenv("MCP_BEARER_TOKEN", "dev-mcp-token")
        self.outbound_query_policy = outbound_query_policy

    def search_external(
        self,
        query: str,
        lang: str = "ja",
        sources: Sequence[str] = ("web", "news"),
    ) -> list[ExternalResult]:
        results: list[ExternalResult] = []
        if "web" in sources:
            res = invoke_mcp_tool(
                "web_search",
                "search_web",
                {"tenant_id": self.tenant_id, "query": query, "lang": lang, "max_results": 3},
                bearer_token=self.bearer_token,
                outbound_query_policy=self.outbound_query_policy,
            )
            for item in res["data"].get("results", []):
                results.append(
                    ExternalResult(
                        text=f"{item.get('title', '')}: {item.get('snippet', '')}",
                        source_url=str(item.get("url", "")),
                        retrieved_at=str(item.get("retrieved_at", "")),
                        source_kind="web",
                        external=True,
                    )
                )
        if "news" in sources:
            res = invoke_mcp_tool(
                "news_search",
                "search_news",
                {"tenant_id": self.tenant_id, "query": query, "lang": lang},
                bearer_token=self.bearer_token,
                outbound_query_policy=self.outbound_query_policy,
            )
            for art in res["data"].get("articles", []):
                results.append(
                    ExternalResult(
                        text=str(art.get("title", "")),
                        source_url=str(art.get("source_url", "")),
                        retrieved_at=str(art.get("retrieved_at", "")),
                        source_kind="news",
                        external=True,
                    )
                )
        return results


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: `uv run python -m alba_one.mcp_client.client --list-tools`."""
    parser = argparse.ArgumentParser(description="ALBA ONE MCP Client Tool Discovery CLI")
    parser.add_argument("--list-tools", action="store_true", help="Print all discovered MCP tools with server and class")
    parser.add_argument("--agent", default=None, help="Filter tools by agent role allowlist")
    parser.add_argument("--profile", default=None, help="Filter tools by compose profile (core|domain|external|all)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    tools = discover_registered_tools(agent_role=args.agent, profile_filter=args.profile)
    if args.json:
        print(json.dumps({"tool_count": len(tools), "tools": tools}, ensure_ascii=False, indent=2))
        return 0

    print(f"ALBA ONE MCP Client — Discovered {len(tools)} tools across {len({t['mcp_server'] for t in tools})} servers:")
    print(f"{'SERVER':<22} {'TOOL':<32} {'CLASS':<10} {'PROFILE':<10} {'PORT':<6} REQUIRED_ARGS")
    print("-" * 105)
    for t in tools:
        req = ", ".join(t["required_args"])
        print(
            f"{t['mcp_server']:<22} {t['tool_name']:<32} {t['class']:<10} "
            f"{t['profile']:<10} {t['port']:<6} [{req}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
