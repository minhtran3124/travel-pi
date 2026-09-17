"""Country ORM model."""

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Country(UUIDBase):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # "VN"
    name: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    # Curated COUNTRIES seed order so the repo can ORDER BY it (dashboard region tiles).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Unique index on name so City.country (a name) can FK against it.
    __table_args__ = (Index("ix_countries_name", "name", unique=True),)
