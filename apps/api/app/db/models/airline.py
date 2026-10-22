"""Airline ORM model. ``position`` is load-bearing for flight determinism: the repo MUST ``ORDER BY position``."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Airline(UUIDBase):
    __tablename__ = "airlines"

    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
