"""Data-access layer for bookings — SQLAlchemy ORM persistence, nothing else.

Business rules live in services/booking_service.py. This tier maps Booking
ORM rows to/from the Booking Pydantic model and nothing more.
"""

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.crud.base import Repo
from app.db import models
from app.db.base import Base
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
    )


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

    def get(self, booking_id: str) -> Booking | None:
        with self._session() as s:
            row = s.get(models.Booking, booking_id)
            return _row_to_booking(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> Booking | None:
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(models.Booking.idempotency_key == key)
            ).first()
            return _row_to_booking(row) if row is not None else None

    def get_by_confirmation_code(self, code: str) -> Booking | None:
        with self._session() as s:
            row = s.scalars(
                select(models.Booking).where(
                    models.Booking.confirmation_code == code.strip().upper()
                )
            ).first()
            return _row_to_booking(row) if row is not None else None

    def list_all(self) -> list[Booking]:
        with self._session() as s:
            rows = s.scalars(
                select(models.Booking).order_by(models.Booking.created_at.desc())
            ).all()
            return [_row_to_booking(r) for r in rows]

    def update_status(self, booking_id: str, status: str) -> bool:
        with self._session() as s:
            row = s.get(models.Booking, booking_id)
            if row is None:
                return False
            row.status = status
            self._commit(s)
            return True

    def add(self, booking: Booking, idempotency_key: str | None = None) -> Booking:
        row = models.Booking(
            id=booking.id,
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
        )
        try:
            with self._session() as s:
                s.add(row)
                self._commit(s)
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return booking
