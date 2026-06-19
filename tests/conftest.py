"""Shared fixtures for all endpoint tests."""

import pytest
from app.crud.flight import FlightIndexRepository
from app.db.engine import get_session_factory
from app.main import create_app
from app.services import flight_service, saved_place_service
from app.services.booking_service import BookingService, get_booking_service
from app.services.saved_place_service import SavedPlaceService, get_saved_place_service
from app.services.trip_service import TripService, get_trip_service
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Return a SQLite URL for an isolated per-session test database."""
    db_file = tmp_path_factory.mktemp("data") / "test_travel.db"
    return f"sqlite:///{db_file}"


@pytest.fixture(scope="session")
def client(tmp_db):
    """TestClient that uses an isolated booking store."""
    svc = BookingService(tmp_db)
    svc.init_db()

    # Point flight-ID persistence at the temp DB too, so flight lookups stay
    # isolated from the real travel.db.
    flight_service.set_index_repo(FlightIndexRepository(get_session_factory(tmp_db)))

    trip_svc = TripService(tmp_db)
    trip_svc.init_db()

    sp_svc = SavedPlaceService(tmp_db)
    sp_svc.init_db()
    # place_service.resolve() reaches the saved store via the module singleton
    # (a direct factory call, not FastAPI DI), so point that singleton at the
    # temp DB too — otherwise shortlisting a saved place can't resolve it.
    saved_place_service._saved_place_service = sp_svc

    app = create_app()
    app.dependency_overrides[get_booking_service] = lambda: svc
    app.dependency_overrides[get_trip_service] = lambda: trip_svc
    app.dependency_overrides[get_saved_place_service] = lambda: sp_svc

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


def get_first_flight_booking_fields(client: TestClient) -> dict:
    """Return the friendly identifier fields for booking the first flight.

    The booking endpoint identifies a flight the way an agent does — by
    flight_number + route + date — so this helper builds that bundle from a
    deterministic search. Spread it into a booking payload alongside the
    passenger details.
    """
    flight = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()["results"][0]
    return {
        "flight_number": flight["flight_number"],
        "origin": VALID_ORIGIN,
        "destination": VALID_DESTINATION,
        "departure_date": VALID_DATE,
    }


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
