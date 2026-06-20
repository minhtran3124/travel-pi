"""Shared fixtures for all endpoint tests."""

import os

import pytest
from app.crud.airline import AirlineRepository
from app.crud.airport import AirportRepository
from app.crud.city import CityRepository
from app.crud.country import CountryRepository
from app.crud.flight import FlightIndexRepository
from app.crud.hotel_ref import HotelRepository
from app.crud.place_ref import PlaceRepository
from app.crud.tip import TipRepository
from app.crud.visa import VisaRepository
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.routers import cities as cities_router
from app.routers import dashboard as dashboard_router
from app.services import (
    airport_service,
    board_service,
    flight_service,
    hotel_service,
    place_service,
    routing_service,
    tip_service,
    visa_service,
)
from app.services.booking_service import BookingService
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Return the DB URL the test suite should run against.

    Defaults to a per-session temp **SQLite** file (zero-config, what local +
    CI runs use). When ``TEST_DATABASE_URL`` is set — the docker-compose.test.yml
    path — return that instead, so the suite genuinely exercises Postgres and
    proves cross-engine parity. The repos' ``init_db()`` (called by the service
    fixtures below) runs ``create_all`` on whichever engine this URL selects, so
    the schema exists either way.
    """
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return override
    db_file = tmp_path_factory.mktemp("data") / "test_travel.db"
    return f"sqlite:///{db_file}"


@pytest.fixture(scope="session")
def client(tmp_db):
    """TestClient bound to an isolated temp DB via a get_session override."""
    # create_all builds every table on the temp DB — the write stores
    # (bookings/trips/saved_places/flight_index) and the reference tables alike.
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)

    # Point flight-ID persistence at the temp DB too, so flight lookups stay
    # isolated from the real travel.db.
    flight_service.set_index_repo(FlightIndexRepository(get_session_factory(tmp_db)))

    # Schema exists; seed the read-only reference entities so DB-backed reads
    # have data. Idempotent, so safe even on the Postgres TEST_DATABASE_URL path.
    seed_all(get_session_factory(tmp_db))

    # Reference-data services hold module-level repo singletons built from the
    # real DATABASE_URL at import time. They are NOT FastAPI dependencies, so
    # dependency_overrides can't reach them — repoint each one at the seeded
    # temp DB (mirrors flight_service.set_index_repo above). Enumerate every
    # migrated service here as the migration progresses.
    sf = get_session_factory(tmp_db)
    flight_service.set_airline_repo(AirlineRepository(sf))
    airport_service.set_airport_repo(AirportRepository(sf))
    board_service.set_airline_repo(AirlineRepository(sf))
    visa_service.set_visa_repo(VisaRepository(sf))
    visa_service.set_city_repo(CityRepository(sf))
    visa_service.set_country_repo(CountryRepository(sf))
    hotel_service.set_hotel_repo(HotelRepository(sf))
    place_service.set_place_repo(PlaceRepository(sf))
    tip_service.set_tip_repo(TipRepository(sf))
    tip_service.set_city_repo(CityRepository(sf))
    tip_service.set_country_repo(CountryRepository(sf))
    dashboard_router.set_repos(
        airline=AirlineRepository(sf),
        country=CountryRepository(sf),
        city=CityRepository(sf),
        visa=VisaRepository(sf),
        tip=TipRepository(sf),
    )
    cities_router.set_city_repo(CityRepository(sf))
    routing_service.set_city_repo(CityRepository(sf))

    app = create_app()

    # One override replaces the per-service repointing the write stores used to
    # need: every service/router that Depends(get_session) now resolves to a
    # request-scoped session on the temp DB (shared transaction per request).
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

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def booking_service(tmp_db):
    """A BookingService bound to a fresh session on the temp DB."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with get_session_factory(tmp_db)() as session:
        yield BookingService(session)


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
