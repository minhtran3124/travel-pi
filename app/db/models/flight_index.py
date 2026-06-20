"""FlightIndex ORM model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class FlightIndex(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "flight_index"

    flight_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    departure_date: Mapped[str] = mapped_column(String, nullable=False)
