"""User ORM model — per-user profile for tier/capability resolution.

Stores the identity tier (free / premium) keyed on the external user_id string
(e.g. Supabase UID). Tier is BE-resolved only; it is never accepted from the
request body. No UUID surrogate key — the external id IS the PK.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    tier: Mapped[str] = mapped_column(String, nullable=False, default="free")
