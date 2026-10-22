"""GET /bookings?trip_id= filters to the caller's own bookings for that trip."""

from __future__ import annotations

import pytest
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.repositories.user import UserRepository
from app.services import hotel_service
from fastapi.testclient import TestClient

from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    get_first_flight_booking_fields,
    get_first_hotel_id,
)

USER_A = "list-trip-filter-owner"
USER_B = "list-trip-filter-intruder"


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    """Pin hotel availability high so a hotel booking here always succeeds."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


def _client_as(tmp_db, user_id: str) -> TestClient:
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
        "passenger_name": "List Trip Filter Test",
        "passenger_email": "listtripfilter@example.com",
        "passenger_phone": "+84 901 234 567",
        **overrides,
    }


def _hotel_payload(client: TestClient, **overrides) -> dict:
    return {
        "hotel_id": get_first_hotel_id(client),
        "check_in": VALID_CHECK_IN,
        "check_out": VALID_CHECK_OUT,
        "guest_name": "List Trip Filter Test",
        "guest_email": "listtripfilter@example.com",
        "guest_phone": "+84 901 234 567",
        **overrides,
    }


def test_trip_id_filter_returns_only_that_trips_bookings(tmp_db):
    with _client_as(tmp_db, USER_A) as c:
        trip_a = c.post("/trips", json={"title": "Trip A"}).json()["id"]
        trip_b = c.post("/trips", json={"title": "Trip B"}).json()["id"]

        c.post("/flights/book", json=_flight_payload(c, trip_id=trip_a))
        c.post("/hotels/book", json=_hotel_payload(c, trip_id=trip_a))
        c.post("/flights/book", json=_flight_payload(c, trip_id=trip_b))
        c.post("/hotels/book", json=_hotel_payload(c))  # unlinked

        filtered = c.get("/bookings", params={"trip_id": trip_a})
        assert filtered.status_code == 200
        filtered_body = filtered.json()
        assert filtered_body["total"] == 2
        assert {b["trip_id"] for b in filtered_body["results"]} == {trip_a}

        unfiltered = c.get("/bookings")
        assert unfiltered.status_code == 200
        assert unfiltered.json()["total"] == 4


def test_trip_id_filter_never_shows_another_users_booking(tmp_db):
    with _client_as(tmp_db, USER_A) as c_a:
        shared_trip_id = c_a.post("/trips", json={"title": "A's trip"}).json()["id"]
        c_a.post("/flights/book", json=_flight_payload(c_a, trip_id=shared_trip_id))

    with _client_as(tmp_db, USER_B) as c_b:
        # B must never see A's booking when querying by A's trip_id.
        resp = c_b.get("/bookings", params={"trip_id": shared_trip_id})

    assert resp.status_code == 200
    assert resp.json()["results"] == []
