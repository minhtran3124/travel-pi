"""Cross-user access to bookings (SC-2, security hardening).

Bookings are now owner-scoped: a booking is stamped with the authenticated
caller's id, and every read/cancel path resolves through that id. The tests
that matter are the negative ones — user B must not be able to see, look up by
confirmation code, or cancel user A's booking, and must be told **"not found"**
(404), never "forbidden" (a 403 would confirm a guessed id is real).

A "user A can read their own booking" case proves nothing about the hole; the
owner case here exists only to prove the scoping did not simply break bookings
for everyone.
"""

from __future__ import annotations

import pytest
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.services import hotel_service
from fastapi.testclient import TestClient

from tests.conftest import get_first_flight_booking_fields

USER_A = "owner-a"
USER_B = "intruder-b"


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    """Pin hotel availability high so any hotel booking here always succeeds."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


def _client_as(tmp_db, user_id: str | None) -> TestClient:
    """A TestClient acting as ``user_id``, or unauthenticated when None."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    seed_all(get_session_factory(tmp_db))
    app = create_app()

    def _session():
        s = get_session_factory(tmp_db)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            id=user_id, email=f"{user_id}@test", role=None, claims={}
        )
    return TestClient(app)


def _book_flight_as(tmp_db, user_id: str) -> dict:
    """Create a flight booking owned by ``user_id`` and return its response."""
    with _client_as(tmp_db, user_id) as c:
        r = c.post(
            "/flights/book",
            json={
                **get_first_flight_booking_fields(c),
                "passenger_name": "Owner A",
                "passenger_email": "owner-a@example.com",
                "passenger_phone": "+84 901 234 567",
            },
        )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def a_booking(tmp_db) -> dict:
    """A flight booking owned by USER_A (id + confirmation_code)."""
    return _book_flight_as(tmp_db, USER_A)


# ---------------------------------------------------------------------------
# Unauthenticated → 401
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_list_bookings(tmp_db):
    with _client_as(tmp_db, None) as c:
        assert c.get("/bookings").status_code == 401


def test_unauthenticated_cannot_read_a_booking(tmp_db, a_booking):
    with _client_as(tmp_db, None) as c:
        assert c.get(f"/bookings/{a_booking['id']}").status_code == 401


def test_unauthenticated_cannot_cancel_a_booking(tmp_db, a_booking):
    with _client_as(tmp_db, None) as c:
        assert c.post(f"/bookings/{a_booking['id']}/cancel").status_code == 401


def test_unauthenticated_cannot_book_a_flight(tmp_db):
    with _client_as(tmp_db, None) as c:
        r = c.post(
            "/flights/book",
            json={
                "flight_number": "VN123",
                "origin": "DAD",
                "destination": "SGN",
                "departure_date": "2026-06-01",
                "passenger_name": "x",
                "passenger_email": "x@test",
                "passenger_phone": "+84 901 234 567",
            },
        )
    assert r.status_code == 401


def test_unauthenticated_cannot_book_a_hotel(tmp_db):
    with _client_as(tmp_db, None) as c:
        r = c.post(
            "/hotels/book",
            json={
                "hotel_id": "any",
                "check_in": "2026-06-01",
                "check_out": "2026-06-03",
                "guests": 1,
                "guest_name": "x",
                "guest_email": "x@test",
                "guest_phone": "+84 901 234 567",
            },
        )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Another user's booking is invisible, not forbidden
# ---------------------------------------------------------------------------


def test_other_users_booking_is_not_listed(tmp_db, a_booking):
    with _client_as(tmp_db, USER_B) as c:
        body = c.get("/bookings", params={"limit": 500}).json()
    ids = [b["id"] for b in body["results"]]
    assert a_booking["id"] not in ids
    assert ids == [], "B owns no bookings, so B's list must be empty"


def test_other_user_cannot_read_the_booking_by_id(tmp_db, a_booking):
    with _client_as(tmp_db, USER_B) as c:
        r = c.get(f"/bookings/{a_booking['id']}")
    assert r.status_code == 404, "must not be 403 — that would confirm the id"


def test_other_user_cannot_read_the_booking_by_confirmation_code(tmp_db, a_booking):
    with _client_as(tmp_db, USER_B) as c:
        r = c.get(f"/bookings/{a_booking['confirmation_code']}")
    assert r.status_code == 404, "confirmation code must not leak across users"


def test_other_user_cannot_cancel_the_booking(tmp_db, a_booking):
    with _client_as(tmp_db, USER_B) as c:
        r = c.post(f"/bookings/{a_booking['id']}/cancel")
    assert r.status_code == 404


def test_other_user_cancel_does_not_actually_cancel(tmp_db, a_booking):
    """A 404 that still performed the write would be the worst outcome."""
    with _client_as(tmp_db, USER_B) as c:
        c.post(f"/bookings/{a_booking['id']}/cancel")
    with _client_as(tmp_db, USER_A) as c:
        r = c.get(f"/bookings/{a_booking['id']}")
    assert r.status_code == 200
    assert r.json()["status"] != "cancelled", "B managed to cancel A's booking"


# ---------------------------------------------------------------------------
# Owner keeps full access (guards against "broken for everyone")
# ---------------------------------------------------------------------------


def test_owner_can_read_and_list_their_booking(tmp_db, a_booking):
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/bookings/{a_booking['id']}").status_code == 200
        assert c.get(f"/bookings/{a_booking['confirmation_code']}").status_code == 200
        ids = [
            b["id"] for b in c.get("/bookings", params={"limit": 500}).json()["results"]
        ]
    assert a_booking["id"] in ids
