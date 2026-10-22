"""SavedPlace ORM model."""

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class SavedPlace(UUIDBase):
    __tablename__ = "saved_places"

    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    favorite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    visited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)
