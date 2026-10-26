"""Layer 5: Tool Guardrail (`guardrails/tool_layer.py`).

Enforces:
1. Per-MCP-server tool allowlist and explicit tool classification (`read` | `write` | `external`).
2. JSON-schema argument validation (`validate_tool_arguments_schema`).
3. Mandatory Outbound Query Guardrail (`check_outbound_query`) on every `external` tool call
   before any query leaves our network (PII/secret scrubbing + tenant sensitive-term check).
4. SQL guard for `sql_readonly` tools: SELECT-only, allowlisted views (`ALLOWED_EXTRACTION_VIEWS`),
   no `;` multi-statements, no DDL/DML, row limit (`<= 500`), and statement timeout (`<= 5000ms`).
5. SSRF & domain allowlist for `external` tools (`web_search`, `news_search`, etc.).
6. All `write`-class tools require a verified human approval (`approval_id`) via the HITL guardrail.
7. Scans tool output text for prompt injection and PII before returning to the planner.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Literal
from urllib.parse import urlparse

from alba_one.guardrails.guardrails_ai import validate_tool_arguments_schema
from alba_one.guardrails.outbound_query import OutboundQueryPolicyType, check_outbound_query
from alba_one.guardrails.types import GuardrailContext, GuardrailResult, build_guardrail_result
from alba_one.kb.extractors import ALLOWED_EXTRACTION_VIEWS
from alba_one.kb.pii import PIIRedactor
from alba_one.retrieval.guardrail_stub import has_prompt_injection

ToolClassType = Literal["read", "write", "external"]

TOOL_CATALOG: dict[tuple[str, str], dict[str, Any]] = {
    ("knowledge_base", "kb_search"): {"class": "read", "required_args": ["tenant_id", "query"]},
    ("knowledge_base", "kb_get_chunk"): {"class": "read", "required_args": ["tenant_id", "chunk_id"]},
    ("knowledge_base", "kb_get_entity"): {"class": "read", "required_args": ["tenant_id", "entity_type"]},
    ("knowledge_base", "kb_list_entities"): {"class": "read", "required_args": ["tenant_id"]},
    ("sql_readonly", "query_view"): {"class": "read", "required_args": ["tenant_id", "sql"]},
    ("departments", "get_department_metrics"): {"class": "read", "required_args": ["tenant_id", "department"]},
    ("departments", "get_signoff_status"): {"class": "read", "required_args": ["tenant_id", "department"]},
    ("approvals", "request_approval"): {"class": "write", "required_args": ["tenant_id", "decision_id"]},
    ("approvals", "check_approval_status"): {"class": "read", "required_args": ["tenant_id", "decision_id"]},
    ("approvals", "list_pending"): {"class": "read", "required_args": ["tenant_id"]},
    ("experiment_tracking", "list_experiments"): {"class": "read", "required_args": ["tenant_id"]},
    ("experiment_tracking", "get_run"): {"class": "read", "required_args": ["tenant_id", "experiment_id"]},
    ("experiment_tracking", "compare_runs"): {"class": "read", "required_args": ["tenant_id", "baseline_id", "candidate_id"]},
    ("experiment_tracking", "get_model_versions"): {"class": "read", "required_args": ["tenant_id", "model_family"]},
    ("experiment_tracking", "get_release_readiness_summary"): {"class": "read", "required_args": ["tenant_id", "version_tag"]},
    ("experiment_tracking", "calculate_model_release_tradeoffs"): {"class": "read", "required_args": ["tenant_id"]},
    ("benchmark_registry", "get_benchmark_results"): {"class": "read", "required_args": ["tenant_id", "version_tag"]},
    ("benchmark_registry", "compare_regressions"): {"class": "read", "required_args": ["tenant_id", "baseline_tag", "candidate_tag"]},
    ("decision_history", "search_similar_decisions"): {"class": "read", "required_args": ["tenant_id", "query"]},
    ("decision_history", "get_decision_record"): {"class": "read", "required_args": ["tenant_id", "decision_id"]},
    ("memory", "search_memories"): {"class": "read", "required_args": ["tenant_id", "user_id", "query"]},
    ("memory", "list_my_memories"): {"class": "read", "required_args": ["tenant_id", "user_id"]},
    ("memory", "delete_memory"): {"class": "write", "required_args": ["tenant_id", "user_id", "memory_id"]},
    ("memory", "propose_memory"): {"class": "write", "required_args": ["tenant_id", "user_id", "content"]},
    ("delivery_planning", "analyze_delivery_routes"): {"class": "read", "required_args": ["tenant_id"]},
    ("delivery_planning", "calculate_sla_breach_probability"): {"class": "read", "required_args": ["tenant_id"]},
    ("delivery_planning", "calculate_route_cost_jpy"): {"class": "read", "required_args": ["tenant_id"]},
    ("staffing", "analyze_staff_shifts"): {"class": "read", "required_args": ["tenant_id"]},
    ("staffing", "calculate_overtime_margin"): {"class": "read", "required_args": ["tenant_id"]},
    ("vessel_allocation", "analyze_berth_allocation"): {"class": "read", "required_args": ["tenant_id"]},
    ("vessel_allocation", "calculate_berth_ukc_margin"): {"class": "read", "required_args": ["tenant_id"]},
    ("document_extraction", "extract_onprem_document"): {"class": "read", "required_args": ["tenant_id", "uri"]},
    ("deployment_status", "get_environment_status"): {"class": "read", "required_args": ["tenant_id", "environment"]},
    ("web_search", "search_web"): {"class": "external", "required_args": ["query"]},
    ("web_search", "fetch_page"): {"class": "external", "required_args": ["url"]},
    ("news_search", "search_news"): {"class": "external", "required_args": ["query"]},
    ("competitor_intel", "track_competitor_releases"): {"class": "external", "required_args": ["query"]},
    ("model_benchmarks", "lookup_public_benchmarks"): {"class": "external", "required_args": ["query"]},
    ("papers", "search_papers"): {"class": "external", "required_args": ["query"]},
    ("github_releases", "list_repo_releases"): {"class": "external", "required_args": ["repo"]},
    ("market_data", "get_market_indices"): {"class": "external", "required_args": ["index_code"]},
    ("weather_marine", "get_port_weather"): {"class": "external", "required_args": ["port_code"]},
    ("regulatory_jp", "lookup_jp_regulation"): {"class": "external", "required_args": ["topic"]},
}

ALLOWED_EXTERNAL_DOMAINS: frozenset[str] = frozenset(
    {
        "albaconnect.co.jp",
        "jma.go.jp",
        "mlit.go.jp",
        "e-gov.go.jp",
        "arxiv.org",
        "semanticscholar.org",
        "huggingface.co",
        "github.com",
        "weather.example.jp",
        "maritime-news.example.com",
    }
)

_FORBIDDEN_SQL_RE = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|PG_SLEEP)\b",
    re.IGNORECASE,
)


def check_sql_guard(sql: str, ctx: GuardrailContext, *, max_rows: int = 500) -> GuardrailResult:
    """Validate that a SQL query is a single read-only SELECT against allowlisted views."""
    cleaned = sql.strip()
    if ";" in cleaned.rstrip(";"):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="sql_guard_no_multi_statement",
            ctx=ctx, details={"sql": cleaned},
        )
    if not cleaned.upper().startswith("SELECT"):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="sql_guard_select_only",
            ctx=ctx, details={"sql": cleaned},
        )
    if _FORBIDDEN_SQL_RE.search(cleaned):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="sql_guard_forbidden_keyword",
            ctx=ctx, details={"sql": cleaned},
        )
    if not any(view in cleaned for view in ALLOWED_EXTRACTION_VIEWS):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="sql_guard_allowlisted_views_only",
            ctx=ctx, details={"sql": cleaned, "allowed_views": sorted(ALLOWED_EXTRACTION_VIEWS)},
        )
    enforced_sql = cleaned.rstrip(";")
    if "LIMIT" not in enforced_sql.upper():
        enforced_sql = f"{enforced_sql} LIMIT {max_rows}"
    return build_guardrail_result(
        layer="tool", raw_action="pass", policy="sql_guard_readonly",
        ctx=ctx, details={"statement_timeout_ms": 5000, "max_rows": max_rows},
        sanitized_payload=enforced_sql,
    )


def check_ssrf_and_domain_allowlist(url: str, ctx: GuardrailContext) -> GuardrailResult:
    """Block private/loopback/metadata IPs (SSRF) and non-allowlisted external domains."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http") or not host:
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="ssrf_invalid_url_scheme",
            ctx=ctx, details={"url": url},
        )
    if host in ("localhost", "0.0.0.0") or host.endswith(".internal") or host.endswith(".local"):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="ssrf_local_host_blocked",
            ctx=ctx, details={"host": host},
        )
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return build_guardrail_result(
                layer="tool", raw_action="block", policy="ssrf_private_or_metadata_ip_blocked",
                ctx=ctx, details={"ip": str(ip)},
            )
    except ValueError:
        pass

    if not any(host == d or host.endswith(f".{d}") for d in ALLOWED_EXTERNAL_DOMAINS):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="external_domain_allowlist",
            ctx=ctx, details={"host": host, "allowed_domains": sorted(ALLOWED_EXTERNAL_DOMAINS)},
        )
    return build_guardrail_result(
        layer="tool", raw_action="pass", policy="external_domain_allowlist",
        ctx=ctx, sanitized_payload=url,
    )


def check(
    payload: dict[str, Any],
    ctx: GuardrailContext,
    *,
    outbound_query_policy: OutboundQueryPolicyType = "generalize",
) -> GuardrailResult:
    """Layer 5 `check(payload, ctx) -> GuardrailResult` for tool calls and tool outputs."""
    server = str(payload.get("mcp_server", ""))
    tool = str(payload.get("tool_name", ""))
    args: dict[str, Any] = dict(payload.get("arguments") or {})
    tool_output: str | None = payload.get("tool_output")

    spec = TOOL_CATALOG.get((server, tool))
    if spec is None:
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="mcp_tool_allowlist",
            ctx=ctx, details={"mcp_server": server, "tool_name": tool},
        )

    schema_res = validate_tool_arguments_schema(args, spec["required_args"], ctx)
    if schema_res.details.get("detected_action") == "block":
        return schema_res

    tool_class: ToolClassType = spec["class"]
    if tool_class == "write" and not payload.get("approval_id") and not payload.get("user_confirmed"):
        return build_guardrail_result(
            layer="tool", raw_action="block", policy="write_tool_requires_hitl_approval",
            ctx=ctx, details={"mcp_server": server, "tool_name": tool, "tool_class": "write"},
        )

    if server == "sql_readonly" and "sql" in args:
        sql_res = check_sql_guard(str(args["sql"]), ctx)
        if sql_res.details.get("detected_action") == "block":
            return sql_res

    if tool_class == "external":
        for url_key in ("target_url", "url"):
            if url_key in args and args[url_key]:
                ssrf_res = check_ssrf_and_domain_allowlist(str(args[url_key]), ctx)
                if ssrf_res.details.get("detected_action") == "block":
                    return ssrf_res
        for q_key in ("query", "topic", "repo"):
            if q_key in args and args[q_key]:
                pol = payload.get("outbound_query_policy", outbound_query_policy)
                oq_res = check_outbound_query(str(args[q_key]), ctx, policy_mode=pol)
                if oq_res.details.get("detected_action") == "block":
                    return oq_res
                if oq_res.details.get("detected_action") == "mask":
                    args[q_key] = oq_res.sanitized_payload
                    return build_guardrail_result(
                        layer="tool", raw_action="mask", policy=oq_res.policy,
                        ctx=ctx, details=oq_res.details, sanitized_payload=args,
                    )

    if tool_output:
        inj = has_prompt_injection(tool_output)
        if inj:
            return build_guardrail_result(
                layer="tool", raw_action="block", policy="tool_output_prompt_injection_scan",
                ctx=ctx, details={"mcp_server": server, "tool_name": tool, "matched": inj},
            )
        pii = PIIRedactor().redact(tool_output)
        if pii.contains_pii:
            return build_guardrail_result(
                layer="tool", raw_action="mask", policy="tool_output_pii_mask",
                ctx=ctx, details={"mcp_server": server, "tool_name": tool, "pii_counts": pii.counts},
                sanitized_payload=pii.redacted_text,
            )

    return build_guardrail_result(
        layer="tool", raw_action="pass", policy="tool_guardrail_clean",
        ctx=ctx, details={"mcp_server": server, "tool_name": tool, "tool_class": tool_class},
        sanitized_payload=tool_output if tool_output is not None else args,
    )
