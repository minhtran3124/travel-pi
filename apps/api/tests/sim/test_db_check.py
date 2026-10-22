"""Read-only DB check: sim-user + since scoping, and the non-sim port guard."""

from datetime import datetime, timezone

import pytest
from app.enums import BookingType
from app.repositories.booking import BookingRepository
from app.repositories.trip import TripRepository
from app.schemas.booking import Booking, FlightBookingDetails
from app.schemas.trip import Trip
from sim.db_check import sim_session_factory, snapshot

SINCE = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _booking(booking_id, created_at):
    return Booking(
        id=booking_id,
        type=BookingType.FLIGHT,
        reference_id="ref-1",
        customer_name="Sim Traveller",
        customer_email="sim@example.com",
        total_price=100.0,
        created_at=created_at,
        details=FlightBookingDetails(
            flight_id="ref-1",
            flight_number="VN123",
            airline="Vietnam Airlines",
            origin="DAD",
            destination="SGN",
            departure_time="2026-06-01T08:30:00",
            arrival_time="2026-06-01T10:00:00",
            passenger_name="Sim Traveller",
        ),
    )


def _trip(trip_id, created_at):
    return Trip(
        id=trip_id,
        title="Sim Trip",
        travelers=1,
        created_at=created_at,
    )


def _factory(tmp_path):
    sf = sim_session_factory(f"sqlite:///{tmp_path / 'sim.db'}", allow_any=True)
    BookingRepository(sf).init_db()
    return sf


def test_snapshot_returns_only_sim_user_rows_after_since(tmp_path):
    sf = _factory(tmp_path)
    bookings = BookingRepository(sf)
    trips = TripRepository(sf)

    bookings.add(_booking("00000000-0000-0000-0000-000000000001", BEFORE), "sim-a")
    bookings.add(_booking("00000000-0000-0000-0000-000000000002", AFTER), "sim-a")
    bookings.add(_booking("00000000-0000-0000-0000-000000000003", AFTER), "other-user")
    trips.create_trip(_trip("10000000-0000-0000-0000-000000000001", BEFORE), "sim-a")
    trips.create_trip(_trip("10000000-0000-0000-0000-000000000002", AFTER), "sim-a")
    trips.create_trip(
        _trip("10000000-0000-0000-0000-000000000003", AFTER), "other-user"
    )

    result = snapshot(sf, user_id="sim-a", since=SINCE)

    assert [b.id for b in result["bookings"]] == [
        "00000000-0000-0000-0000-000000000002"
    ]
    assert [t.id for t in result["trips"]] == ["10000000-0000-0000-0000-000000000002"]


def test_snapshot_treats_naive_created_at_as_utc(tmp_path):
    sf = _factory(tmp_path)
    bookings = BookingRepository(sf)

    naive_before = datetime(2026, 5, 1, 12, 0)
    naive_after = datetime(2026, 7, 1, 12, 0)
    bookings.add(
        _booking("00000000-0000-0000-0000-0000000000a1", naive_before), "sim-a"
    )
    bookings.add(_booking("00000000-0000-0000-0000-0000000000a2", naive_after), "sim-a")

    result = snapshot(sf, user_id="sim-a", since=SINCE)

    assert [b.id for b in result["bookings"]] == [
        "00000000-0000-0000-0000-0000000000a2"
    ]


def test_sim_session_factory_refuses_non_sim_port():
    with pytest.raises(ValueError):
        sim_session_factory("postgresql+psycopg://x@localhost:5433/travel")
