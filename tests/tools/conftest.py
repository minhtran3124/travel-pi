"""Fixtures for tool tests (specs/travel-agent Phase 3).

Tools resolve their DB session from ``get_settings().database_url`` (they run
inside the graph, not a request), so these fixtures point that setting at an
isolated temp SQLite DB and seed reference data once.
"""

import pytest
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.schemas.trip import TripCreate
from app.services.trip_service import TripService


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Point DATABASE_URL at a fresh seeded temp DB; return its URL."""
    url = f"sqlite:///{tmp_path / 'tools.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


@pytest.fixture
def trip_id(agent_db):
    """Create a trip on the agent DB and return its id."""
    with get_session_factory(agent_db)() as s:
        trip = TripService(s).create_trip(TripCreate(title="Tokyo trip", city="Tokyo"))
        s.commit()
        return trip.id
