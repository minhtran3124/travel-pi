"""Place ORM model.

Carries every field the ``app/schemas/place.py`` ``Place`` model requires so
``Place.model_validate(row, from_attributes=True)`` validates. ``id`` is the
UUID string stored verbatim; ``short_code`` is a computed Pydantic property.
"""

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID string, verbatim
    # PLACES list seed order so place_repo.all()/search() can ORDER BY it — the
    # deterministic base/tiebreaker order under place_service's stable sort.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price_level: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_hours: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
