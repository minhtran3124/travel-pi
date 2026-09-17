"""User ORM model. Tier is BE-resolved only, never accepted from the request body; the external id IS the PK."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.enums import Tier


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Plain string value, no native enum column; ``Tier`` is the source of truth.
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    tier: Mapped[str] = mapped_column(String, nullable=False, default=Tier.FREE.value)
