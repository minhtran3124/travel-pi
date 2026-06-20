"""City ORM model.

``country`` is the country *name* (not code) and FKs to ``countries.name``
(the unique index defined on the ``Country`` model); ``country_code`` is a
denormalized convenience column filled by the seeder.
"""

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class City(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cities"

    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(
        ForeignKey("countries.name"), nullable=False
    )  # the country NAME
    country_code: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # denormalized
    airport_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_cities_name_country", "name", "country", unique=True),)
