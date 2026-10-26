"""FastAPI routes for Decisions, HITL Approvals, Outcomes & Steward Write-Backs (`api/decisions.py`).

All endpoints use `/api/v1/...` per Phase 7 User Answer 0:
- `POST /api/v1/decisions`
- `GET /api/v1/decisions`
- `GET /api/v1/decisions/{decision_id}`
- `POST /api/v1/approvals/{decision_id}/decide` (returns HTTP 202 Accepted; HTTP 409 on stale hash/version)
- `POST /api/v1/decisions/{decision_id}/outcomes`
- `POST /api/v1/outcomes/{outcome_id}/write-back`
- `GET /api/v1/outcomes/stats`
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from alba_one.agents.hitl.service import HITLAuthorizationError, StaleApprovalConflictError
from alba_one.agents.workflow import DecisionOSWorkflowService
from alba_one.core.tenancy import get_tenant_context, get_user_context
from alba_one.schemas.common import TenantContext, UserContext

router = APIRouter(tags=["decisions", "approvals", "outcomes"])
_workflow_svc: DecisionOSWorkflowService | None = None


def get_workflow_service() -> DecisionOSWorkflowService:
    global _workflow_svc
    if _workflow_svc is None:
        _workflow_svc = DecisionOSWorkflowService()
    return _workflow_svc


@router.post("/api/v1/decisions", status_code=status.HTTP_201_CREATED)
async def create_decision_endpoint(
    payload: dict[str, Any],
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Start a decision workflow (`Ask -> Gather -> Hypothesise -> Judge -> awaiting_approval`)."""
    svc = get_workflow_service()
    return svc.create_decision(
        question=str(payload["query"]),
        tenant_id=tenant.tenant_id,
        requester_id=user.user_id,
        workflow=str(payload.get("workflow_domain", "delivery_planning")),
        lang=str(payload.get("language", user.language.value)),
    )


@router.get("/api/v1/decisions")
async def list_decisions_endpoint(
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """List decisions scoped to the caller's tenant."""
    svc = get_workflow_service()
    items = [d for d in svc.decisions.values() if d["tenant_id"] == tenant.tenant_id]
    return {"tenant_id": tenant.tenant_id, "user_id": user.user_id, "items": items}


@router.get("/api/v1/decisions/{decision_id}")
async def get_decision_endpoint(
    decision_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    svc = get_workflow_service()
    dec = svc.decisions.get(decision_id)
    if dec is None or dec["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")
    return dec


@router.post("/api/v1/approvals/{decision_id}/decide", status_code=status.HTTP_202_ACCEPTED)
async def decide_approval_endpoint(
    decision_id: str,
    payload: dict[str, Any],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Record a human `ApprovalAction` (`approver_id` and `approver_role` from auth context) and enqueue outbox resume."""
    svc = get_workflow_service()
    try:
        return svc.hitl.submit_decision(
            decision_id=decision_id,
            tenant_id=tenant.tenant_id,
            authenticated_user_id=user.user_id,
            authenticated_role=user.role.value,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except StaleApprovalConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message_ja": exc.message_ja, "message_en": exc.message_en},
        ) from exc
    except HITLAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/v1/decisions/{decision_id}/outcomes", status_code=status.HTTP_201_CREATED)
async def submit_outcome_endpoint(
    decision_id: str,
    payload: dict[str, Any],
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Submit an outcome review (`write_back_approved` is rejected here; requires separate steward call)."""
    svc = get_workflow_service()
    dec = svc.decisions.get(decision_id)
    if dec is None or dec["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")
    try:
        return svc.outcomes.submit_outcome_review(
            decision_record=dec,
            reviewer_id=user.user_id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/api/v1/outcomes/{outcome_id}/write-back")
async def approve_outcome_writeback_endpoint(
    outcome_id: str,
    payload: dict[str, Any],
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Separate knowledge_steward write-back gate (`WRITEBACK_REQUIRES_DIFFERENT_PERSON=true`)."""
    svc = get_workflow_service()
    try:
        return svc.outcomes.approve_lesson_writeback(
            outcome_id=outcome_id,
            tenant_id=tenant.tenant_id,
            steward_user_id=user.user_id,
            steward_role=user.role.value,
            edited_statement_ja=str(payload["statement_ja"]),
            edited_statement_en=str(payload["statement_en"]),
            approved=bool(payload.get("approved", True)),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/api/v1/outcomes/stats")
async def get_outcome_stats_endpoint(
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Return decision-quality calibration statistics (gated by `MIN_OUTCOMES_FOR_STATS`)."""
    svc = get_workflow_service()
    return svc.outcomes.compute_decision_quality_stats(tenant_id=tenant.tenant_id)
