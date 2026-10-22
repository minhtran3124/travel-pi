"""Airport ORM model."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Airport(UUIDBase):
    __tablename__ = "airports"

    iata: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str] = mapped_column(
        ForeignKey("countries.code"), nullable=False
    )
    # AIRPORTS insertion order so the repo can ORDER BY it.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
