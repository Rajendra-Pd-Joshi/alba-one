"""FastAPI exception handlers wrapping `AlbaError` with structured trace IDs."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from alba_one.core.error_catalog import AlbaError
from alba_one.core.logging import trace_id_var


def register_exception_handlers(app: FastAPI) -> None:
    """Attach bilingual JSON exception handlers to the FastAPI application."""

    @app.exception_handler(AlbaError)
    async def handle_alba_error(request: Request, exc: AlbaError) -> JSONResponse:
        trace_id = trace_id_var.get() or request.headers.get("x-trace-id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(trace_id=trace_id),
        )
