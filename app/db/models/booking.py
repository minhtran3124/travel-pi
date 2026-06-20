"""Booking ORM model."""

from sqlalchemy import JSON, Float, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Booking(UUIDBase):
    __tablename__ = "bookings"

    type: Mapped[str] = mapped_column(String, nullable=False)
    reference_id: Mapped[str] = mapped_column(String, nullable=False)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    customer_email: Mapped[str] = mapped_column(String, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmation_code: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "ix_bookings_idempotency_key",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_bookings_confirmation_code",
            "confirmation_code",
            unique=True,
            sqlite_where=text("confirmation_code IS NOT NULL"),
            postgresql_where=text("confirmation_code IS NOT NULL"),
        ),
    )
