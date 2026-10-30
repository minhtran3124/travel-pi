"""Shared fixtures for all endpoint tests."""

import os

import pytest
from app.core.auth import AuthUser, get_current_user
from app.core.dashboard_auth import DashboardUser, get_current_dashboard_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.repositories.user import UserRepository
from app.services import weather_service
from app.services.booking_service import BookingService
from fastapi.testclient import TestClient

from tests.fixtures.light_app import ensure_seeded

# Keep `make test` zero-config and fast: no bot heartbeat task (tests that need it build their own).
os.environ.setdefault("BOT_HEARTBEAT_ENABLED", "false")


@pytest.fixture(autouse=True)
def _clear_geocode_cache():
    """Reset the process-wide geocode cache around every test to keep it hermetic."""
    weather_service.clear_geocode_cache()
    yield
    weather_service.clear_geocode_cache()


@pytest.fixture(autouse=True)
def _clear_live_registry():
    """Idle chat sessions outlive their turn in the process-wide live registry, so isolate every test from the last."""
    from app.agents.live_registry import registry

    registry.clear()
    yield
    registry.clear()


@pytest.fixture(autouse=True)
def _no_llm_semaphore(monkeypatch):
    """Keep the per-process LLM semaphore off by default so mocked/fake models stay plain; its own tests opt in."""
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_GLOBAL_CONCURRENCY", "0")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Return the DB URL to test against: temp SQLite by default, or TEST_DATABASE_URL when set."""
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return override
    db_file = tmp_path_factory.mktemp("data") / "test_travel.db"
    return f"sqlite:///{db_file}"


DEFAULT_TEST_USER_ID = "test-user-1"


@pytest.fixture(scope="session")
def client(tmp_db):
    """TestClient bound to an isolated temp DB via a get_session override."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)

    # Seed read-only reference entities; idempotent, so safe on the Postgres path too.
    seed_all(get_session_factory(tmp_db))

    # Seed the shared test caller as premium so book-route tests aren't gated to 403.
    UserRepository(get_session_factory(tmp_db)).upsert_tier(
        DEFAULT_TEST_USER_ID, "premium"
    )

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

    # Supabase auth isn't configured in tests; override required-auth with a fixed traveller.
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id=DEFAULT_TEST_USER_ID, email="test@example.com", role=None, claims={}
    )

    # Dashboard login isn't configured in tests; override the guard (specs/dashboard-auth-required D9).
    app.dependency_overrides[get_current_dashboard_user] = lambda: DashboardUser(
        username="test-ops"
    )

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
    ensure_seeded(tmp_db)
    with get_session_factory(tmp_db)() as session:
        yield session


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
    """Return the identifier fields (flight_number + route + date) for booking the first flight."""
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
