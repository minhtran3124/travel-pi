"""Data-access layer for bookings — SQLAlchemy ORM persistence, nothing else.

Business rules live in services/booking_service.py. This tier maps Booking
ORM rows to/from the Booking Pydantic model and nothing more.
"""

import hashlib

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.base import Base
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
    """Map an owner id to a stable signed-int64 Postgres advisory-lock key (gh-198).

    ``pg_advisory_xact_lock`` takes a ``bigint``, so we hash the owner id to a
    deterministic 64-bit signed integer. blake2b (not Python ``hash()``, which is
    salted per process) keeps the key identical across processes and workers so
    two requests by the same owner contend on the same lock.

    :param user_id: The owner whose per-owner lock key to derive.
    :return: A stable signed 64-bit lock key for that owner.
    """
    digest = hashlib.blake2b(f"booking:{user_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class BookingRepository(Repo):
    """SQLAlchemy-backed store of booking rows."""

    def init_db(self) -> None:
        Base.metadata.create_all(self._bind(), checkfirst=True)

    def ping(self) -> bool:
        # Cheap reachability check that does NOT require the table to exist
        # (parity with the old bare "SELECT 1").
        with self._session() as s:
            s.execute(text("SELECT 1"))
        return True

    def get(self, booking_id: str, user_id: str) -> Booking | None:
        """Return the caller's booking by UUID, or None.

        A booking owned by someone else returns ``None`` — the same answer as a
        booking that does not exist, so a probe cannot tell a real id from a
        foreign one (#118).

        :param booking_id: The booking's UUID.
        :param user_id: The caller; rows owned by anyone else are invisible.
        :return: The booking, or None when missing or not the caller's.
        """
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.id == booking_id,
                    models.Booking.user_id == user_id,
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def get_by_idempotency_key(self, key: str, user_id: str) -> Booking | None:
        """Replay lookup, scoped to the caller (#118).

        The idempotency index is global, so without the owner filter a replay
        could hand one user another user's booking whenever their keys collided.

        :param key: The idempotency key supplied by the client.
        :param user_id: The caller; another owner's booking is not a replay.
        :return: The caller's booking stored under that key, or None.
        """
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.idempotency_key == key,
                    models.Booking.user_id == user_id,
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def get_by_confirmation_code(self, code: str, user_id: str) -> Booking | None:
        """Return the caller's booking by confirmation code, or None.

        Scoped to the owner so user B cannot resolve user A's booking by
        quoting its friendly code (#118).

        :param code: The 6-char confirmation code (case-insensitive).
        :param user_id: The caller; another owner's booking is invisible.
        :return: The caller's booking with that code, or None.
        """
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.confirmation_code == code.strip().upper(),
                    models.Booking.user_id == user_id,
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def confirmation_code_exists(self, code: str) -> bool:
        """Return True if any booking (any owner) already uses ``code``.

        The ``ix_bookings_confirmation_code`` UNIQUE index spans all rows, so the
        collision check that guards minting must be global — an owner-scoped
        check would miss a collision with another user's code and let the insert
        fail. Never exposes another user's data, only whether a code is taken.

        :param code: The candidate confirmation code (case-insensitive).
        :return: ``True`` if the code is already in use by any booking.
        """
        with self._session() as s:
            row = s.scalars(
                select(models.Booking.id).where(
                    models.Booking.confirmation_code == code.strip().upper()
                )
            ).first()
            return row is not None

    def list_all(self, user_id: str) -> list[Booking]:
        """Return the caller's bookings, newest first.

        :param user_id: The owner whose bookings to return.
        :return: The caller's bookings, newest first.
        """
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
        """Return the caller's non-cancelled bookings for one referenced item.

        Owner-scoped and excludes cancelled rows, newest first — this is the
        candidate set the opt-in duplicate-intent check scans for a same-flight
        or same-hotel match (gh-194). A cancelled booking never counts, so it
        cannot block a re-book of the same flight/hotel.

        :param user_id: The owner whose bookings to search.
        :param booking_type: ``"flight"`` or ``"hotel"``.
        :param reference_id: The ``flight_id`` or ``hotel_id`` to match on.
        :return: The caller's active bookings for that reference, newest first.
        """
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
        """Take a per-owner advisory lock for the duplicate check + insert (gh-198).

        The gh-194 duplicate-intent check reads ``list_active_by_reference`` and
        then inserts; two concurrent requests by the same owner can both pass the
        read and both insert. The caller (``BookingService``) takes this lock at
        the top of its ``check_duplicate`` block so the check + insert is
        serialized per owner: the loser waits, then sees the winner's row.

        The caller MUST own the transaction — this is a transaction-scoped lock
        (``pg_advisory_xact_lock``), released automatically on commit or rollback,
        never explicitly. In factory mode there is no caller-owned transaction, so
        this raises ``RuntimeError`` rather than lock-then-immediately-release.

        On SQLite this is intentionally a no-op: SQLite backs only the unit-test
        suite, and every running environment is Postgres. There is no cross-engine
        parity to keep here — the lock is a Postgres concurrency guard, not a
        business rule.

        :param user_id: The owner whose booking writes to serialize.
        """
        if self._s is None:
            raise RuntimeError(
                "lock_owner_bookings requires a live caller-owned session "
                "(transaction-scoped advisory lock); factory mode has no "
                "transaction to attach the lock to."
            )
        with self._session() as s:
            if s.get_bind().dialect.name == "postgresql":
                s.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": _owner_lock_key(user_id)},
                )

    def list_all_unscoped(self) -> list[Booking]:
        """Return every booking, newest first — operator dashboard only.

        The one deliberately unscoped read: the dashboard ledger shows all
        bookings across users. No user-facing route may call this.

        :return: Every booking, newest first.
        """
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
        """Set the status of the caller's booking. No-op for a foreign id.

        When ``release_idempotency_key`` is True the row's ``idempotency_key`` is
        cleared in the same transaction, so a cancelled booking is never a replay
        target: a later booking under the same key creates a fresh row instead of
        returning the cancelled one (gh-193). The column is nullable and its
        unique index is partial (excludes NULL), so clearing it never collides.

        :param booking_id: The booking's UUID.
        :param user_id: The caller; a booking owned by anyone else is not found.
        :param status: The new status value.
        :param release_idempotency_key: When True, also clear the row's
            ``idempotency_key`` so the booking can no longer be replayed.
        :return: ``True`` if the caller's row was found and updated.
        """
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
        """Insert a booking, stamping the owner (#118).

        :param booking: The booking to insert.
        :param user_id: The owner stamped on the row; every later read filters
            by it.
        :param idempotency_key: Key stored on the row for replay detection.
        :return: The inserted booking, or the winning booking from a concurrent
            request that raced on the same ``idempotency_key``.
        """
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
