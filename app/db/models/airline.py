"""Airline ORM model.

The ``position`` column is load-bearing for flight determinism:
``flight_service.generate_flights`` does ``rng.choice(AIRLINES)`` over a
*seeded* RNG, so the seed order must be preserved and the repo MUST
``ORDER BY position``.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Airline(Base):
    __tablename__ = "airlines"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # AIRLINES seed order
    color: Mapped[str | None] = mapped_column(String, nullable=True)  # AIRLINE_COLORS
