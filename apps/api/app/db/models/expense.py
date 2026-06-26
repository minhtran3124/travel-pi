"""Expense ORM model — on-trip spend ledger entry."""

from sqlalchemy import Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Expense(UUIDBase):
    __tablename__ = "expenses"

    trip_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    fx_rate: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[str] = mapped_column(String, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "ix_expenses_trip_id_live",
            "trip_id",
            postgresql_where="deleted_at IS NULL",
        ),
    )
