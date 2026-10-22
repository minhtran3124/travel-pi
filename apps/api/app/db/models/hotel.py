"""Hotel ORM model. ``short_code`` is not a column — it is a computed Pydantic property derived from ``id``."""

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Hotel(UUIDBase):
    __tablename__ = "hotels"

    # HOTELS seed order so the repo can ORDER BY it (stable pagination base).
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
