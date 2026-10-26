"""Health check endpoints (`/api/v1/health`, `/api/v1/health/deep`, `/health`, `/health/deep`)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from alba_one.core.config import get_settings
from alba_one.core.health import run_deep_health_check

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
@router.get("/health")
async def health_liveness() -> dict[str, Any]:
    """Fast liveness and configuration sanity endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "product": "ALBA ONE",
        "company": "ALBACONNECT Inc.",
        "environment": settings.app_env,
        "default_language": settings.default_language,
        "gateway_provider": settings.gateway_provider,
        "eval_judge_warning": settings.eval_judge_warning(),
    }


@router.get("/api/v1/health/deep")
@router.get("/health/deep")
async def health_deep(
    live_network: bool | None = Query(
        default=None,
        description="Override STARTUP_PING_ENABLED to force live network pings to Pinecone/Bedrock/Gateway",
    ),
) -> dict[str, Any]:
    """Deep dependency health report for Postgres, Redis, Pinecone, Bedrock, and all models."""
    settings = get_settings()
    return await run_deep_health_check(settings=settings, probe_external_network=live_network)
