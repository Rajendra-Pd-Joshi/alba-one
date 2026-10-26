"""Pure-Python handlers for ALBA ONE domain & internal MCP servers (`mcp_servers/domain_handlers.py`).

Used by both the FastMCP `server.py` entrypoints and the contract/evaluation test suites.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from alba_one.mcp_servers.knowledge_base.service import KnowledgeBaseService
from alba_one.memory.long_term import InMemoryLongTermAdapter, MemoryService

_KB_SVC: KnowledgeBaseService | None = None
_MEM_SVC: MemoryService | None = None
_APPROVAL_STORE: dict[str, dict[str, Any]] = {
    "dec_demo_001": {
        "approval_id": "apr_demo_001",
        "decision_id": "dec_demo_001",
        "tenant_id": "tenant_alba_demo",
        "status": "approved_with_conditions",
        "approver_role": "Port Operations Director",
        "conditions": ["Monitor gust wind speed every 30 minutes at Berth TYO-B3."],
    },
    "dec_demo_002": {
        "approval_id": "apr_demo_002",
        "decision_id": "dec_demo_002",
        "tenant_id": "tenant_alba_demo",
        "status": "pending",
        "approver_role": "AI Governance Lead",
        "conditions": [],
    },
}


def _kb() -> KnowledgeBaseService:
    global _KB_SVC
    if _KB_SVC is None:
        _KB_SVC = KnowledgeBaseService.create_demo_default()
    return _KB_SVC


def _mem() -> MemoryService:
    global _MEM_SVC
    if _MEM_SVC is None:
        _MEM_SVC = MemoryService(adapter=InMemoryLongTermAdapter())
    return _MEM_SVC


def handle_kb_search(args: dict[str, Any]) -> dict[str, Any]:
    hits = _kb().kb_search(
        tenant_id=str(args["tenant_id"]),
        caller_role=str(args.get("caller_role", "analyst")),
        query=str(args["query"]),
        lang=args.get("lang"),
        entity_type=args.get("entity_type"),
        top_k=int(args.get("top_k", 5)),
    )
    return {"tenant_id": str(args["tenant_id"]), "hits": hits}


def handle_kb_get_chunk(args: dict[str, Any]) -> dict[str, Any]:
    return _kb().kb_get_chunk(
        tenant_id=str(args["tenant_id"]),
        caller_role=str(args.get("caller_role", "analyst")),
        chunk_id=str(args["chunk_id"]),
    )


def handle_kb_get_entity(args: dict[str, Any]) -> dict[str, Any]:
    return _kb().kb_get_entity(
        tenant_id=str(args["tenant_id"]),
        caller_role=str(args.get("caller_role", "analyst")),
        entity_type=str(args["entity_type"]),
    )


def handle_kb_list_entities(args: dict[str, Any]) -> dict[str, Any]:
    entities = _kb().kb_list_entities(
        tenant_id=str(args["tenant_id"]),
        caller_role=str(args.get("caller_role", "analyst")),
    )
    return {"tenant_id": str(args["tenant_id"]), "entities": entities}


def handle_sql_query_view(args: dict[str, Any]) -> dict[str, Any]:
    sql = str(args["sql"])
    max_rows = min(int(args.get("max_rows", 100)), 500)
    rows = [
        {"row_index": 1, "tenant_id": str(args["tenant_id"]), "summary": "DBA read-only view row 1"},
        {"row_index": 2, "tenant_id": str(args["tenant_id"]), "summary": "DBA read-only view row 2"},
    ][:max_rows]
    return {"sql_executed": sql, "statement_timeout_ms": 5000, "row_count": len(rows), "rows": rows}


def handle_department_metrics(args: dict[str, Any]) -> dict[str, Any]:
    dept = str(args["department"]).lower()
    metrics_map = {
        "finance": {"budget_utilization_pct": 84.2, "reallocation_cap_jpy": 5_000_000, "currency": "JPY"},
        "hr": {"article36_monthly_limit_hours": 45.0, "max_current_overtime_hours": 41.5, "compliant": True},
        "ops": {"on_time_berth_rate_pct": 94.8, "cold_chain_sla_breaches": 0},
        "legal_compliance": {"isms_status": "ISO/IEC 27001 certified", "pending_audits": 0},
        "sales": {"pharma_tier1_accounts": 12, "sla_penalty_exposure_jpy": 0},
        "engineering": {"canary_error_rate_pct": 0.12, "p95_latency_ms": 420.0},
    }
    return {
        "tenant_id": str(args["tenant_id"]),
        "department": dept,
        "period": str(args.get("period", "2026-Q3")),
        "metrics": metrics_map.get(dept, {"status": "available"}),
    }


def handle_department_signoff(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "department": str(args["department"]),
        "decision_id": str(args.get("decision_id", "dec_demo_001")),
        "signoff_status": "approved",
        "reviewer_role": f"{args['department']}_lead",
    }


def handle_request_approval(args: dict[str, Any]) -> dict[str, Any]:
    dec_id = str(args["decision_id"])
    record = {
        "approval_id": f"apr_{dec_id}",
        "decision_id": dec_id,
        "tenant_id": str(args["tenant_id"]),
        "status": "pending",
        "approver_role": str(args.get("approver_role", "Director")),
        "conditions": list(args.get("conditions", [])),
    }
    _APPROVAL_STORE[dec_id] = record
    return record


def handle_check_approval_status(args: dict[str, Any]) -> dict[str, Any]:
    dec_id = str(args["decision_id"])
    return _APPROVAL_STORE.get(
        dec_id,
        {"approval_id": f"apr_{dec_id}", "decision_id": dec_id, "tenant_id": str(args["tenant_id"]), "status": "pending"},
    )


def handle_list_pending_approvals(args: dict[str, Any]) -> dict[str, Any]:
    t_id = str(args["tenant_id"])
    pending = [v for v in _APPROVAL_STORE.values() if v.get("tenant_id") == t_id and v.get("status") == "pending"]
    return {"tenant_id": t_id, "pending_count": len(pending), "items": pending}


def handle_list_experiments(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "experiments": [
            {"experiment_id": "exp_neptune_v24", "name": "ALBA-NEPTUNE-V2.4-Routing", "status": "completed"},
            {"experiment_id": "exp_neptune_v23", "name": "ALBA-NEPTUNE-V2.3-Baseline", "status": "completed"},
        ],
    }


def handle_get_run(args: dict[str, Any]) -> dict[str, Any]:
    exp_id = str(args["experiment_id"])
    return {
        "tenant_id": str(args["tenant_id"]),
        "experiment_id": exp_id,
        "metrics": {"ndcg_at_10": 0.892, "p95_latency_ms": 385.0, "hallucination_rate": 0.008},
    }


def handle_compare_runs(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "baseline_id": str(args["baseline_id"]),
        "candidate_id": str(args["candidate_id"]),
        "deltas": {"ndcg_at_10_delta": 0.031, "p95_latency_ms_delta": -25.0, "regression_detected": False},
    }


def handle_get_model_versions(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "model_family": str(args["model_family"]),
        "versions": [
            {"version_tag": "ALBA-NEPTUNE-V2.3", "stage": "Production"},
            {"version_tag": "ALBA-NEPTUNE-V2.4", "stage": "Staging"},
        ],
    }


def handle_release_readiness(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "version_tag": str(args["version_tag"]),
        "ready_for_canary": True,
        "safety_eval_passed": True,
        "required_approver_role": "AI Governance Lead",
    }


def handle_benchmark_results(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "version_tag": str(args["version_tag"]),
        "suite": "alba_internal_maritime_v2",
        "scores": {"jp_contract_qa_f1": 0.914, "en_logistics_qa_f1": 0.928, "safety_refusal_accuracy": 0.995},
    }


def handle_compare_regressions(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "baseline_tag": str(args["baseline_tag"]),
        "candidate_tag": str(args["candidate_tag"]),
        "has_blocking_regression": False,
        "summary": "Candidate improves JP contract QA F1 by +2.4% with zero safety regressions.",
    }


def handle_search_similar_decisions(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "query": str(args["query"]),
        "matches": [
            {
                "decision_id": "dec_hist_2026_019",
                "title": "横浜港強風時の医薬品定温コンテナ優先着岸および名古屋バイパス判断",
                "outcome_score": 0.94,
                "approved_by_role": "Port Operations Director",
            }
        ],
    }


def handle_get_decision_record(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(args["tenant_id"]),
        "decision_id": str(args["decision_id"]),
        "chosen_hypothesis": "H1: Berth VSL-SAKURA-01 at TYO-B3 with refrigerated truck standby",
        "approval_status": "approved_with_conditions",
        "outcome_review": "SLA met with 0 cold-chain excursions; cost delta +420,000 JPY.",
    }


DOMAIN_TOOL_HANDLERS: dict[tuple[str, str], Callable[[dict[str, Any]], dict[str, Any]]] = {
    ("knowledge_base", "kb_search"): handle_kb_search,
    ("knowledge_base", "kb_get_chunk"): handle_kb_get_chunk,
    ("knowledge_base", "kb_get_entity"): handle_kb_get_entity,
    ("knowledge_base", "kb_list_entities"): handle_kb_list_entities,
    ("sql_readonly", "query_view"): handle_sql_query_view,
    ("departments", "get_department_metrics"): handle_department_metrics,
    ("departments", "get_signoff_status"): handle_department_signoff,
    ("approvals", "request_approval"): handle_request_approval,
    ("approvals", "check_approval_status"): handle_check_approval_status,
    ("approvals", "list_pending"): handle_list_pending_approvals,
    ("experiment_tracking", "list_experiments"): handle_list_experiments,
    ("experiment_tracking", "get_run"): handle_get_run,
    ("experiment_tracking", "compare_runs"): handle_compare_runs,
    ("experiment_tracking", "get_model_versions"): handle_get_model_versions,
    ("experiment_tracking", "get_release_readiness_summary"): handle_release_readiness,
    ("benchmark_registry", "get_benchmark_results"): handle_benchmark_results,
    ("benchmark_registry", "compare_regressions"): handle_compare_regressions,
    ("decision_history", "search_similar_decisions"): handle_search_similar_decisions,
    ("decision_history", "get_decision_record"): handle_get_decision_record,
}
