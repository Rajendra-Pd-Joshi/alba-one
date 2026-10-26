"""SQLAlchemy 2.0 declarative base and tenant-isolation mixins."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Boolean, DateTime, Select, String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ALBA ONE SQLAlchemy ORM models."""


class TenantScopedMixin:
    """Mixin enforcing `tenant_id`, `lang`, `is_synthetic`, and timestamps on rows."""

    tenant_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    lang: Mapped[str] = mapped_column(String(8), default="ja", nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


ModelT = TypeVar("ModelT", bound=TenantScopedMixin)


def select_for_tenant(model: type[ModelT], tenant_id: str) -> Select[tuple[ModelT]]:
    """Build a SELECT statement strictly scoped to a single `tenant_id` (Principle 8).

    Raises ValueError if `tenant_id` is empty so callers can never accidentally
    query across tenants.
    """
    cleaned = tenant_id.strip()
    if not cleaned:
        raise ValueError("tenant_id is required for all tenant-scoped queries.")
    return select(model).where(model.tenant_id == cleaned)


def assert_same_tenant(record: Any, expected_tenant_id: str) -> None:
    """Verify that a loaded ORM instance or dict belongs to `expected_tenant_id`."""
    actual = getattr(record, "tenant_id", None)
    if actual is None and isinstance(record, dict):
        actual = record.get("tenant_id")
    if not expected_tenant_id or actual != expected_tenant_id:
        raise PermissionError(
            f"Tenant isolation violation: expected '{expected_tenant_id}', got '{actual}'."
        )
