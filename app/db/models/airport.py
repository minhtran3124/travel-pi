"""Airport ORM model."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Airport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "airports"

    iata: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str] = mapped_column(
        ForeignKey("countries.code"), nullable=False
    )
    # AIRPORTS dict insertion order (the order board_service originally sampled
    # from) so airport_repo.list() can ORDER BY it — restores pre-migration
    # board parity and stable /airports listing across engines.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
