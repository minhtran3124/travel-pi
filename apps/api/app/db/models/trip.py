"""Trip, TripItem, and TripPlaceLink ORM models."""

from sqlalchemy import JSON, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Trip(UUIDBase):
    __tablename__ = "trips"

    # Owner (#118). Every read and write is scoped to it — before this column a
    # trip belonged to nobody, so `list_trips()` returned every trip in the
    # database and a guessed UUID reached anyone's itinerary. NOT NULL from the
    # first revision: the migration deletes the pre-existing ownerless rows
    # rather than leaving a nullable column whose meaning drifts.
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    travelers: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)
    budget_caps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        # Uniqueness is per owner (#118). A global unique key meant two users
        # sending the same Idempotency-Key collided: the second one's
        # owner-scoped replay lookup finds nothing, the global index still
        # rejects the INSERT, and the IntegrityError fallback re-runs the same
        # scoped lookup and re-raises — a 500 instead of that user's trip.
        Index(
            "ix_trips_user_idempotency_key",
            "user_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class TripItem(UUIDBase):
    __tablename__ = "trip_items"

    trip_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    place_id: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_id: Mapped[str | None] = mapped_column(String, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )

    __table_args__ = (
        Index(
            "ix_trip_items_idempotency_key",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


class TripPlaceLink(UUIDBase):
    __tablename__ = "trip_place_link"

    trip_id: Mapped[str] = mapped_column(String, nullable=False)
    place_id: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    added_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index(
            "ix_trip_place_link_unique",
            "trip_id",
            "place_id",
            "source",
            unique=True,
        ),
    )
