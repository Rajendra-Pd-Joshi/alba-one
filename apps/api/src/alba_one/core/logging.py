"""Structured JSON logging with `trace_id`, `request_id`, and `tenant_id` contextvars."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="")


def set_request_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, str]:
    """Bind trace_id, request_id, and tenant_id to the current async context."""
    resolved_trace = trace_id or trace_id_var.get() or f"tr_{uuid.uuid4().hex[:16]}"
    resolved_req = request_id or request_id_var.get() or f"req_{uuid.uuid4().hex[:12]}"
    resolved_tenant = tenant_id if tenant_id is not None else tenant_id_var.get()
    trace_id_var.set(resolved_trace)
    request_id_var.set(resolved_req)
    tenant_id_var.set(resolved_tenant)
    return {
        "trace_id": resolved_trace,
        "request_id": resolved_req,
        "tenant_id": resolved_tenant,
    }


class StructuredJSONFormatter(logging.Formatter):
    """Formats Python log records as single-line JSON objects with trace & tenant metadata."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id_var.get() or None,
            "request_id": request_id_var.get() or None,
            "tenant_id": tenant_id_var.get() or None,
        }
        extra_fields = getattr(record, "structured_data", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root/application logger with `StructuredJSONFormatter`."""
    logger = logging.getLogger("alba_one")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
