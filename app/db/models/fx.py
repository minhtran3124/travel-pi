"""FX rate / currency ORM models."""

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FxRate(Base):
    __tablename__ = "fx_rates"

    code: Mapped[str] = mapped_column(String, primary_key=True)  # ISO 4217
    rate: Mapped[float] = mapped_column(Float, nullable=False)  # units per 1 USD
    name: Mapped[str] = mapped_column(String, nullable=False)  # from CURRENCY_NAMES


class CountryCurrency(Base):
    __tablename__ = "country_currency"

    country: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)


class FxMeta(Base):
    __tablename__ = "fx_meta"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, default=1
    )  # singleton row
    last_updated: Mapped[str] = mapped_column(String, nullable=False)
