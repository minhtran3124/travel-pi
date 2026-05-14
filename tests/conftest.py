"""Shared fixtures for all endpoint tests."""

import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.booking_service import BookingService, get_booking_service


@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Return a path to a temporary SQLite file, unique per test session."""
    db_file = tmp_path_factory.mktemp("data") / "test_travel.db"
    return str(db_file)


@pytest.fixture(scope="session")
def client(tmp_db):
    """TestClient that uses an isolated booking store."""
    svc = BookingService(tmp_db)
    svc.init_db()

    app = create_app()
    app.dependency_overrides[get_booking_service] = lambda: svc

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def booking_service(tmp_db):
    """Return the same BookingService used by the session-scoped client."""
    svc = BookingService(tmp_db)
    svc.init_db()
    return svc


# ---------------------------------------------------------------------------
# Helpers re-used across test modules
# ---------------------------------------------------------------------------

VALID_ORIGIN = "DAD"
VALID_DESTINATION = "SGN"
VALID_DATE = "2026-06-01"
VALID_CHECK_IN = "2026-06-01"
VALID_CHECK_OUT = "2026-06-03"


def get_first_flight_id(client: TestClient) -> str:
    """Return the ID of the first flight from a deterministic search."""
    resp = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    )
    return resp.json()["results"][0]["id"]


def get_first_hotel_id(client: TestClient) -> str:
    """Return the ID of the first hotel in Da Nang."""
    resp = client.get(
        "/hotels/search",
        params={
            "city": "Da Nang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
        },
    )
    return resp.json()["results"][0]["id"]
