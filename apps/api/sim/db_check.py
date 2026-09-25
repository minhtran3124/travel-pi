"""Read-only snapshot of a sim traveller's bookings and trips, with a DB-port guard."""

from datetime import datetime, timezone

from app.db.engine import get_session_factory
from app.repositories.booking import BookingRepository
from app.repositories.trip import TripRepository
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

_SIM_DB_PORT = 5434


def _as_utc(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC so it compares against a tz-aware ``since``."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def snapshot(
    session_factory: "sessionmaker[Session]",
    user_id: str,
    since: datetime,
) -> dict:
    """Return the traveller's bookings and trips created at or after ``since`` (UTC)."""
    bookings = [
        b
        for b in BookingRepository(session_factory).list_all(user_id)
        if _as_utc(b.created_at) >= since
    ]
    trips = [
        t
        for t in TripRepository(session_factory).list_trips(user_id)
        if _as_utc(t.created_at) >= since
    ]
    return {"bookings": bookings, "trips": trips}


def sim_session_factory(
    url: str,
    allow_any: bool = False,
) -> "sessionmaker[Session]":
    """Build a session factory for ``url``, refusing any port other than the sim DB's."""
    if not allow_any and make_url(url).port != _SIM_DB_PORT:
        raise ValueError(
            f"refusing DB URL on port {make_url(url).port!r}; expected {_SIM_DB_PORT} "
            "(pass allow_any=True to override)"
        )
    return get_session_factory(url)
