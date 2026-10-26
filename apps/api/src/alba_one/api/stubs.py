"""# STUB: Placeholder FastAPI routers for `chat`, `kb/pillars`, and `guardrail_events`.

(`tools` graduated in Phase 5; `decisions`, `approvals`, and `outcomes` graduated in Phase 7;
`metrics` and `evals` graduated to `alba_one.api.metrics` in Phase 9.)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from alba_one.core.tenancy import get_tenant_context, get_user_context
from alba_one.schemas.common import TenantContext, UserContext

chat_router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
kb_router = APIRouter(prefix="/api/v1/kb", tags=["kb"])
guardrail_events_router = APIRouter(prefix="/api/v1/guardrail-events", tags=["guardrail_events"])


@kb_router.get("/pillars")
async def list_pillars(
    tenant: TenantContext = Depends(get_tenant_context),
    user: UserContext = Depends(get_user_context),
) -> dict[str, Any]:
    """Return the three exact ALBA ONE product pillars in the user's active language."""
    return {
        "tenant_id": tenant.tenant_id,
        "language": user.language.value,
        "pillars": [
            {
                "id": "business_meaning_and_data",
                "ja": "業務の意味とデータの接続",
                "en": "Business meaning and data",
            },
            {
                "id": "workflow_decision_support",
                "ja": "業務ごとの判断支援",
                "en": "Workflow-specific decision support",
            },
            {
                "id": "outcome_and_knowledge_ops",
                "ja": "結果と知識の運用",
                "en": "Outcome and knowledge operations",
            },
        ],
    }
