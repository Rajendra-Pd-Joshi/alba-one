"""FastAPI application entrypoint for ALBA ONE (`alba_one.api.main:app`)."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from alba_one.api.decisions import router as decisions_api_router
from alba_one.api.health import router as health_router
from alba_one.api.kb import router as kb_api_router
from alba_one.api.metrics import router as metrics_router
from alba_one.api.stubs import (
    chat_router,
    guardrail_events_router,
    kb_router,
)
from alba_one.api.tools import router as tools_router
from alba_one.core.config import get_settings
from alba_one.core.errors import register_exception_handlers
from alba_one.core.health import run_deep_health_check
from alba_one.core.logging import configure_logging, set_request_context
from alba_one.core.startup_checks import enforce_startup_checks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run fail-closed startup security checks and health probes before serving traffic."""
    startup_report = enforce_startup_checks(dict(os.environ))
    settings = get_settings()
    logger = configure_logging(settings.log_level)

    for w in startup_report.warnings:
        logger.warning(w)

    warning = settings.eval_judge_warning()
    if warning:
        logger.warning(warning)

    report = await run_deep_health_check(
        settings=settings,
        probe_external_network=settings.startup_ping_enabled,
    )
    app.state.startup_warnings = startup_report.warnings
    logger.info(
        "ALBA ONE startup health check completed",
        extra={"structured_data": {"health_status": report["status"]}},
    )
    yield


def create_app() -> FastAPI:
    """Construct the ALBA ONE FastAPI application with OpenAPI docs disabled in prod by default."""
    raw_env = (os.environ.get("APP_ENV") or "").strip().lower()
    docs_enabled = raw_env in ("development", "test") and (
        os.environ.get("OPENAPI_DOCS_ENABLED", "true").strip().lower() in ("1", "true", "yes")
    )
    app = FastAPI(
        title="ALBA ONE — Decision OS API",
        description="Enterprise Decision OS (意思決定OS) by ALBACONNECT Inc.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    register_exception_handlers(app)

    @app.middleware("http")
    async def attach_trace_and_log(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        ctx = set_request_context(
            trace_id=request.headers.get("x-trace-id"),
            request_id=request.headers.get("x-request-id"),
            tenant_id=request.headers.get("x-tenant-id"),
        )
        response: Response = await call_next(request)
        response.headers["x-trace-id"] = ctx["trace_id"]
        response.headers["x-request-id"] = ctx["request_id"]
        logging.getLogger("alba_one").info(
            f"{request.method} {request.url.path} -> {response.status_code}",
            extra={"structured_data": {"status_code": response.status_code, "path": request.url.path}},
        )
        return response

    app.include_router(health_router)
    app.include_router(kb_api_router)
    app.include_router(tools_router)
    app.include_router(decisions_api_router)
    app.include_router(metrics_router)
    app.include_router(chat_router)
    app.include_router(kb_router)
    app.include_router(guardrail_events_router)
    return app


app = create_app()
