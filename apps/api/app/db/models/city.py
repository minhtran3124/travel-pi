"""City ORM model. ``country`` is the country *name* (FK to ``countries.name``), not the code."""

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class City(UUIDBase):
    __tablename__ = "cities"

    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(ForeignKey("countries.name"), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String, nullable=True)
    airport_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_cities_name_country", "name", "country", unique=True),)
