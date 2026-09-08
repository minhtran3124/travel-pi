"""Tests for the optional ``trip_id`` on flight/hotel bookings (Task 2.1, SC-4).

A booking can be attached to a trip the caller owns; a trip owned by someone
else is refused with 404 (the same #118 not-found-vs-forbidden pattern used
elsewhere); the field stays optional; and idempotent replay is unaffected by
what the (ignored) second request carries.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.enums import BookingStatus, BookingType
from app.main import create_app
from app.repositories.booking import BookingRepository
from app.repositories.user import UserRepository
from app.schemas.booking import Booking, FlightBookingDetails
from app.services import hotel_service
from fastapi.testclient import TestClient

from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    get_first_flight_booking_fields,
    get_first_hotel_id,
)

USER_A = "trip-link-owner"
USER_B = "trip-link-intruder"


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    """Pin hotel availability high so a hotel booking here always succeeds."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


def _client_as(tmp_db, user_id: str) -> TestClient:
    """A premium TestClient acting as ``user_id``, on the shared temp DB."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    seed_all(get_session_factory(tmp_db))
    UserRepository(get_session_factory(tmp_db)).upsert_tier(user_id, "premium")

    app = create_app()

    def _override_get_session():
        session = get_session_factory(tmp_db)()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id=user_id, email=f"{user_id}@test", role=None, claims={}
    )
    return TestClient(app)


def _flight_payload(client: TestClient, **overrides) -> dict:
    return {
        **get_first_flight_booking_fields(client),
        "passenger_name": "Trip Link Test",
        "passenger_email": "triplink@example.com",
        "passenger_phone": "+84 901 234 567",
        **overrides,
    }


def _hotel_payload(client: TestClient, **overrides) -> dict:
    return {
        "hotel_id": get_first_hotel_id(client),
        "check_in": VALID_CHECK_IN,
        "check_out": VALID_CHECK_OUT,
        "guest_name": "Trip Link Test",
        "guest_email": "triplink@example.com",
        "guest_phone": "+84 901 234 567",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Owned trip_id links the booking
# ---------------------------------------------------------------------------


def test_book_flight_with_owned_trip_id_links_it(tmp_db):
    with _client_as(tmp_db, USER_A) as c:
        trip_id = c.post("/trips", json={"title": "A's trip"}).json()["id"]
        resp = c.post("/flights/book", json=_flight_payload(c, trip_id=trip_id))
    assert resp.status_code == 200
    assert resp.json()["trip_id"] == trip_id


def test_book_hotel_with_owned_trip_id_links_it(tmp_db):
    with _client_as(tmp_db, USER_A) as c:
        trip_id = c.post("/trips", json={"title": "A's trip"}).json()["id"]
        resp = c.post("/hotels/book", json=_hotel_payload(c, trip_id=trip_id))
    assert resp.status_code == 200
    assert resp.json()["trip_id"] == trip_id


# ---------------------------------------------------------------------------
# A trip_id owned by someone else -> 404
# ---------------------------------------------------------------------------


def test_book_flight_with_foreign_trip_id_returns_404(tmp_db):
    with _client_as(tmp_db, USER_B) as c_b:
        foreign_trip_id = c_b.post("/trips", json={"title": "B's trip"}).json()["id"]
    with _client_as(tmp_db, USER_A) as c_a:
        resp = c_a.post(
            "/flights/book", json=_flight_payload(c_a, trip_id=foreign_trip_id)
        )
    assert resp.status_code == 404


def test_book_hotel_with_foreign_trip_id_returns_404(tmp_db):
    with _client_as(tmp_db, USER_B) as c_b:
        foreign_trip_id = c_b.post("/trips", json={"title": "B's trip"}).json()["id"]
    with _client_as(tmp_db, USER_A) as c_a:
        resp = c_a.post(
            "/hotels/book", json=_hotel_payload(c_a, trip_id=foreign_trip_id)
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# No trip_id -> still succeeds, trip_id stays null
# ---------------------------------------------------------------------------


def test_book_flight_without_trip_id_still_succeeds_with_null(tmp_db):
    with _client_as(tmp_db, USER_A) as c:
        resp = c.post("/flights/book", json=_flight_payload(c))
    assert resp.status_code == 200
    assert resp.json()["trip_id"] is None


def test_book_hotel_without_trip_id_still_succeeds_with_null(tmp_db):
    with _client_as(tmp_db, USER_A) as c:
        resp = c.post("/hotels/book", json=_hotel_payload(c))
    assert resp.status_code == 200
    assert resp.json()["trip_id"] is None


# ---------------------------------------------------------------------------
# Idempotent replay is unaffected by a different trip_id on the replay
# ---------------------------------------------------------------------------


def test_replay_ignores_different_trip_id_on_second_request(tmp_db):
    with _client_as(tmp_db, USER_A) as c:
        trip_id = c.post("/trips", json={"title": "A's trip"}).json()["id"]
        headers = {"Idempotency-Key": "trip-link-replay-key"}
        first = c.post("/flights/book", json=_flight_payload(c), headers=headers).json()
        second = c.post(
            "/flights/book",
            json=_flight_payload(c, trip_id=trip_id),
            headers=headers,
        ).json()
    assert second["id"] == first["id"]
    assert second["trip_id"] is None


# ---------------------------------------------------------------------------
# Repository round trip: task 1.2's mapping is only proven once the Booking
# schema has a trip_id field to carry the value through.
# ---------------------------------------------------------------------------


def test_repository_round_trip_persists_trip_id(seeded_session):
    booking = Booking(
        id="22222222-3333-4444-5555-666666666666",
        type=BookingType.FLIGHT,
        reference_id="FL_TEST",
        customer_name="Round Trip",
        customer_email="roundtrip@example.com",
        total_price=100.0,
        currency="USD",
        status=BookingStatus.CONFIRMED,
        created_at=datetime.now(timezone.utc),
        details=FlightBookingDetails(
            flight_id="FL_TEST",
            flight_number="VN1",
            airline="Test Air",
            origin="DAD",
            destination="SGN",
            departure_time="2026-06-01T08:00:00",
            arrival_time="2026-06-01T10:00:00",
            passenger_name="Round Trip",
        ),
        trip_id="trip-abc-123",
    )
    repo = BookingRepository(seeded_session)
    repo.add(booking, "round-trip-user")
    fetched = repo.get(booking.id, "round-trip-user")
    assert fetched is not None
    assert fetched.trip_id == "trip-abc-123"
