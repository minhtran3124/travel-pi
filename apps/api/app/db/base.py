"""SQLAlchemy declarative base + shared mixins. Importing has no DB side effects."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models in app.db.models."""


# Stable namespace for deterministic seed UUIDs, identical on every machine and run.
_SEED_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "travel-pi.seed")


def new_uuid() -> str:
    """Return a fresh random UUID4 string — the default PK for runtime rows."""
    return str(uuid.uuid4())


def deterministic_uuid(*parts: str) -> str:
    """Return a stable UUID5 from a natural key, so re-seeds map to the same PK."""
    return str(uuid.uuid5(_SEED_NAMESPACE, ":".join(parts)))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UUIDMixin:
    """Adds a UUID string primary key ``id`` (random UUID4 by default)."""

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)


class TimestampMixin:
    """Adds ISO-8601 ``created_at`` / ``updated_at`` string timestamps."""

    created_at: Mapped[str] = mapped_column(
        String, nullable=False, default=_utc_now_iso
    )
    updated_at: Mapped[str] = mapped_column(
        String, nullable=False, default=_utc_now_iso, onupdate=_utc_now_iso
    )


class UUIDBase(UUIDMixin, TimestampMixin, Base):
    """Standard model base: UUID string PK + ISO-8601 timestamps."""

    __abstract__ = True
