"""Data-access layer for bookings; business rules live in services/booking_service.py."""

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.base import Base
from app.db.locks import advisory_lock_key, advisory_xact_lock
from app.enums import BookingStatus
from app.repositories.base import Repo
from app.schemas.booking import Booking


def _row_to_booking(row: models.Booking) -> Booking:
    details = dict(row.details) if isinstance(row.details, dict) else row.details
    if isinstance(details, dict) and "kind" not in details:
        details["kind"] = row.type
    return Booking(
        id=row.id,
        type=row.type,
        reference_id=row.reference_id,
        customer_name=row.customer_name,
        customer_email=row.customer_email,
        total_price=row.total_price,
        currency=row.currency,
        status=row.status,
        created_at=row.created_at,
        details=details,
        notes=row.notes,
        trip_id=row.trip_id,
    )


def _owner_lock_key(user_id: str) -> int:
    """The signed int64 advisory-lock key for a booking owner; delegates to the
    shared hasher so bookings and other lock users share one mechanism."""
    return advisory_lock_key(f"booking:{user_id}")


class BookingRepository(Repo):
    """SQLAlchemy-backed store of booking rows."""

    def init_db(self) -> None:
        Base.metadata.create_all(self._bind(), checkfirst=True)

    def ping(self) -> bool:
        # Cheap reachability check that does not require the table to exist.
        with self._session() as s:
            s.execute(text("SELECT 1"))
        return True

    def get(self, booking_id: str, user_id: str) -> Booking | None:
        """Return the caller's booking by UUID, or None; a foreign owner's booking is indistinguishable from missing."""
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.id == booking_id,
                    models.Booking.user_id == user_id,
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def get_by_idempotency_key(self, key: str, user_id: str) -> Booking | None:
        """Replay lookup scoped to the caller — the idempotency index is global, so an unscoped match could leak another user's booking."""
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.idempotency_key == key,
                    models.Booking.user_id == user_id,
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def get_by_confirmation_code(self, code: str, user_id: str) -> Booking | None:
        """Return the caller's booking by confirmation code, or None; owner-scoped so a code can't resolve another user's booking."""
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.confirmation_code == code.strip().upper(),
                    models.Booking.user_id == user_id,
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def confirmation_code_exists(self, code: str) -> bool:
        """Return True if any booking (any owner) already uses ``code``; the collision check must be global since the UNIQUE index spans all rows."""
        with self._session() as s:
            row = s.scalars(
                select(models.Booking.id).where(
                    models.Booking.confirmation_code == code.strip().upper()
                )
            ).first()
            return row is not None

    def list_all(self, user_id: str) -> list[Booking]:
        """Return the caller's bookings, newest first."""
        with self._session() as s:
            rows = s.scalars(
                select(models.Booking)
                .where(models.Booking.user_id == user_id)
                .order_by(models.Booking.created_at.desc())
            ).all()
            return [_row_to_booking(r) for r in rows]

    def list_active_by_reference(
        self, user_id: str, booking_type: str, reference_id: str
    ) -> list[Booking]:
        """Return the caller's non-cancelled bookings for one referenced item, newest first — the duplicate-intent candidate set (cancelled rows never block a re-book)."""
        with self._session() as s:
            rows = s.scalars(
                select(models.Booking)
                .where(
                    models.Booking.user_id == user_id,
                    models.Booking.type == booking_type,
                    models.Booking.reference_id == reference_id,
                    models.Booking.status != BookingStatus.CANCELLED.value,
                )
                .order_by(models.Booking.created_at.desc())
            ).all()
            return [_row_to_booking(r) for r in rows]

    def lock_owner_bookings(self, user_id: str) -> None:
        """Take a per-owner transaction-scoped advisory lock (pg_advisory_xact_lock) to serialize the duplicate-check + insert. Requires a caller-owned transaction (factory mode raises); no-op on SQLite."""
        if self._s is None:
            raise RuntimeError(
                "lock_owner_bookings requires a live caller-owned session "
                "(transaction-scoped advisory lock); factory mode has no "
                "transaction to attach the lock to."
            )
        with self._session() as s:
            advisory_xact_lock(s, f"booking:{user_id}")

    def list_all_unscoped(self) -> list[Booking]:
        """Return every booking, newest first — the one deliberately unscoped read (operator dashboard only; no user-facing route)."""
        with self._session() as s:
            rows = s.scalars(
                select(models.Booking).order_by(models.Booking.created_at.desc())
            ).all()
            return [_row_to_booking(r) for r in rows]

    def update_status(
        self,
        booking_id: str,
        user_id: str,
        status: str,
        *,
        release_idempotency_key: bool = False,
    ) -> bool:
        """Set the status of the caller's booking (no-op for a foreign id). When ``release_idempotency_key`` is True, clear the key in the same transaction so a cancelled booking is never a replay target."""
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.id == booking_id,
                    models.Booking.user_id == user_id,
                )
            ).first()
            if row is None:
                return False
            row.status = status
            if release_idempotency_key:
                row.idempotency_key = None
            self._commit(s)
            return True

    def add(
        self, booking: Booking, user_id: str, idempotency_key: str | None = None
    ) -> Booking:
        """Insert a booking, stamping the owner; on an idempotency_key race, return the winner instead of raising."""
        row = models.Booking(
            id=booking.id,
            user_id=user_id,
            type=booking.type.value,
            reference_id=booking.reference_id,
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            total_price=booking.total_price,
            currency=booking.currency,
            status=booking.status.value,
            created_at=booking.created_at.isoformat(),
            details=booking.details.model_dump(mode="json"),
            notes=booking.notes,
            idempotency_key=idempotency_key,
            confirmation_code=booking.confirmation_code,
            trip_id=booking.trip_id,
        )
        try:
            with self._session() as s:
                with s.begin_nested():  # savepoint: keep a shared (UoW) session usable
                    s.add(row)
                self._commit(s)
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_by_idempotency_key(idempotency_key, user_id)
                if existing is not None:
                    return existing
            raise
        return booking
