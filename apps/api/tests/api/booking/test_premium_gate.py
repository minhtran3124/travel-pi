"""Premium gate on the book routes: free tier gets 403, premium still books."""

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

_UID = "gate-user"


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    """Pin hotel availability high so a hotel booking here always succeeds."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


def _make_app(tmp_path, *, premium: bool):
    """App authenticated as ``_UID``, on an isolated DB, seeded premium or left free."""
    url = f"sqlite:///{tmp_path / 'premium_gate.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))

    if premium:
        s = get_session_factory(url)()
        try:
            UserRepository(s).upsert_tier(_UID, "premium")
            s.commit()
        finally:
            s.close()

    app = create_app()

    def _override_get_session():
        session = get_session_factory(url)()
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
        id=_UID, email=None, role=None, claims={}
    )
    return app


def _flight_booking_payload(client: TestClient) -> dict:
    return {
        **get_first_flight_booking_fields(client),
        "passenger_name": "Gate Test",
        "passenger_email": "gate@example.com",
        "passenger_phone": "+84 901 234 567",
    }


def _hotel_booking_payload(client: TestClient) -> dict:
    return {
        "hotel_id": get_first_hotel_id(client),
        "check_in": VALID_CHECK_IN,
        "check_out": VALID_CHECK_OUT,
        "guests": 1,
        "guest_name": "Gate Test",
        "guest_email": "gate@example.com",
        "guest_phone": "+84 901 234 567",
    }


# ---------------------------------------------------------------------------
# Free tier -> 403 PremiumRequiredError
# ---------------------------------------------------------------------------


def test_free_caller_book_flight_returns_403(tmp_path):
    app = _make_app(tmp_path, premium=False)
    with TestClient(app) as c:
        resp = c.post("/flights/book", json=_flight_booking_payload(c))
    assert resp.status_code == 403
    assert resp.json()["error"] == "PremiumRequiredError"


def test_free_caller_book_hotel_returns_403(tmp_path):
    app = _make_app(tmp_path, premium=False)
    with TestClient(app) as c:
        resp = c.post("/hotels/book", json=_hotel_booking_payload(c))
    assert resp.status_code == 403
    assert resp.json()["error"] == "PremiumRequiredError"


# ---------------------------------------------------------------------------
# Premium tier -> booking still succeeds
# ---------------------------------------------------------------------------


def test_premium_caller_book_flight_still_succeeds(tmp_path):
    app = _make_app(tmp_path, premium=True)
    with TestClient(app) as c:
        resp = c.post("/flights/book", json=_flight_booking_payload(c))
    assert resp.status_code == 200
    assert resp.json()["id"]


def test_premium_caller_book_hotel_still_succeeds(tmp_path):
    app = _make_app(tmp_path, premium=True)
    with TestClient(app) as c:
        resp = c.post("/hotels/book", json=_hotel_booking_payload(c))
    assert resp.status_code == 200
    assert resp.json()["id"]
