"""Airport lookup over the DB-backed airport repository."""

from app.core.config import get_settings
from app.crud.airport import AirportRepository
from app.db.engine import get_session_factory
from app.schemas.airport import Airport

# Module-level repo singleton, built from the configured DB. It is NOT a
# FastAPI dependency, so tests repoint it via ``set_airport_repo`` after seeding
# the temp DB (see tests/conftest.py) — the same pattern flight_service uses.
_airport_repo = AirportRepository(get_session_factory(get_settings().database_url))


def set_airport_repo(repo: AirportRepository) -> None:
    """Point airport lookups at a different store — used by tests to read the
    seeded temporary database instead of the real travel.db."""
    global _airport_repo
    _airport_repo = repo


def list_airports() -> list[Airport]:
    """Return the supported airports as a list of ``Airport`` objects."""
    return _airport_repo.list()


def get_airport(code: str) -> Airport | None:
    """Return the airport for an IATA ``code``, or ``None`` if unknown.

    Used by the web pages to show a friendly city / name next to the raw
    3-letter code. Flights can be generated for any code, so callers must
    handle a ``None`` result (just show the bare code in that case).
    """
    return _airport_repo.get(code)
