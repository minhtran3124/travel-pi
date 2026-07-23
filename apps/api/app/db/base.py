"""SQLAlchemy declarative base + shared mixins.

Importing this module has no DB side effects (no engine, no connection); it
only defines the metadata that Alembic autogenerate and create_all read.

Every ORM model mixes in ``UUIDMixin`` (a UUID string primary key) and
``TimestampMixin`` (ISO-8601 ``created_at`` / ``updated_at``). Reference
entities derive a *deterministic* UUID5 from their natural key at seed time
(see ``app/db/seed.py`` → ``deterministic_uuid``) so re-seeding stays
idempotent; runtime entities fall back to a random UUID4 via the column default.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models in app.db.models."""


# Stable namespace for deterministic seed UUIDs. Derived deterministically from
# a fixed string, so it needs no hard-coded literal and is identical on every
# machine and run.
_SEED_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "travel-pi.seed")


def new_uuid() -> str:
    """Return a fresh random UUID4 string — the default PK for runtime rows.

    :return: A random UUID4 string.
    """
    return str(uuid.uuid4())


def deterministic_uuid(*parts: str) -> str:
    """Return a stable UUID5 string derived from a natural key.

    Seeding reference data through this keeps ``session.merge`` idempotent: the
    same natural key always maps to the same primary key across re-seeds.

    :param parts: Natural-key components, joined to form the UUID5 name.
    :return: A stable UUID5 string.
    """
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
    """Standard model base: UUID string PK + ISO-8601 timestamps.

    Every current model wants this exact trio, so they inherit ``UUIDBase``
    instead of repeating ``(UUIDMixin, TimestampMixin, Base)``. The mixins stay
    independently importable for any future table that needs to opt out of one
    of them. ``__abstract__`` keeps SQLAlchemy from mapping this to a table; the
    declarative registry/metadata still lives on ``Base``.
    """

    __abstract__ = True
