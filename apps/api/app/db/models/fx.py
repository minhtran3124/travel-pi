"""FX rate / currency ORM models."""

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class FxRate(UUIDBase):
    __tablename__ = "fx_rates"

    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # ISO 4217
    rate: Mapped[float] = mapped_column(Float, nullable=False)  # units per 1 USD
    name: Mapped[str] = mapped_column(String, nullable=False)  # from CURRENCY_NAMES


class CountryCurrency(UUIDBase):
    __tablename__ = "country_currency"

    country: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String, nullable=False)


class FxMeta(UUIDBase):
    __tablename__ = "fx_meta"

    # Singleton row — seeded with a fixed deterministic id.
    last_updated: Mapped[str] = mapped_column(String, nullable=False)
