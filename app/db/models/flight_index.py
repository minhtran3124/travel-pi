"""FlightIndex ORM model."""

from app.db.base import Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class FlightIndex(Base):
    __tablename__ = "flight_index"

    flight_id: Mapped[str] = mapped_column(String, primary_key=True)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    departure_date: Mapped[str] = mapped_column(String, nullable=False)
