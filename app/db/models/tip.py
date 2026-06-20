"""Tip + CountrySummary ORM models.

Tip ``id`` is a deterministic UUID5 derived from ``(scope, key, position)`` at
seed time — opaque and stable. The ``position`` column preserves the seed list
order, enforced unique per (scope, key).
"""

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Tip(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tips"

    scope: Mapped[str] = mapped_column(String, nullable=False)  # "country" | "city"
    key: Mapped[str] = mapped_column(String, nullable=False)  # country or city name
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_essential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_tips_scope_key_position", "scope", "key", "position", unique=True),
    )


class CountrySummary(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "country_summaries"

    country: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
