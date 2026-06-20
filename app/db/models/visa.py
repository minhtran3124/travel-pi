"""Visa (entry requirements) ORM model."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Visa(UUIDBase):
    __tablename__ = "visa"

    country: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    visa_free_days: Mapped[int] = mapped_column(Integer, nullable=False)
    visa_on_arrival: Mapped[bool] = mapped_column(Boolean, nullable=False)
    e_visa: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passport_validity_months: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
