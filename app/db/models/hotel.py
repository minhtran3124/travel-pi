"""Hotel ORM model.

Carries every field the ``app/schemas/hotel.py`` ``Hotel`` model requires so
``Hotel(**row)`` / ``model_validate(row, from_attributes=True)`` validate.
``country`` is filled at seed time from the city. ``short_code`` is NOT a
column — it is a computed Pydantic property derived from ``id``.
"""

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID string, verbatim
    # HOTELS list seed order so hotel_repo.all()/search() can ORDER BY it —
    # gives /hotels pagination a stable base order across engines.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(
        String, nullable=False
    )  # seed-filled from city
    address: Mapped[str] = mapped_column(String, nullable=False)
    star_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_night: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    amenities: Mapped[list] = mapped_column(JSON, nullable=False)
    image_url: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    property_type: Mapped[str] = mapped_column(String, nullable=False)
    chain: Mapped[str] = mapped_column(String, nullable=False)
    check_in_time: Mapped[str] = mapped_column(String, nullable=False)
    check_out_time: Mapped[str] = mapped_column(String, nullable=False)
    breakfast_included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    free_cancellation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    languages_spoken: Mapped[list] = mapped_column(JSON, nullable=False)
