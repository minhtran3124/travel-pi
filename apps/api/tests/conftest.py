"""Shared fixtures for all endpoint tests."""

import os

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.services import weather_service
from app.services.booking_service import BookingService
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_geocode_cache():
    """Reset the module-level geocode cache around every test.

    ``weather_service.geocode_city`` memoises successful lookups process-wide, so
    without this a city geocoded (with one canned payload) in one test would leak
    a cache hit into the next — which patches ``_fetch_json`` to a different
    payload or an error. Clearing before and after keeps each test hermetic.
    """
    weather_service.clear_geocode_cache()
    yield
    weather_service.clear_geocode_cache()


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

    # Schema exists; seed the read-only reference entities so DB-backed reads
    # have data. Idempotent, so safe even on the Postgres TEST_DATABASE_URL path.
    # Every service/router now resolves its repos from the request session, so
    # the get_session override below is the single seam — no per-service repointing.
    seed_all(get_session_factory(tmp_db))

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


@pytest.fixture()
def seeded_session(tmp_db):
    """A Session on the seeded temp DB — for unit tests that call read services
    (now request-scoped classes) directly instead of through the HTTP client."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    seed_all(get_session_factory(tmp_db))
    with get_session_factory(tmp_db)() as session:
        yield session


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
