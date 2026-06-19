"""Tip + CountrySummary ORM models.

Tip IDs are positional (``tip_{scope}_{prefix}_{NN}``) — the ``position``
column preserves the seed list order, enforced unique per (scope, key).
"""

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tip(Base):
    __tablename__ = "tips"

    id: Mapped[str] = mapped_column(
        String, primary_key=True
    )  # tip_{scope}_{prefix}_{NN}
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


class CountrySummary(Base):
    __tablename__ = "country_summaries"

    country: Mapped[str] = mapped_column(String, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
