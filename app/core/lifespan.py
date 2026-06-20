"""Application lifespan — startup and shutdown hooks.

Importing a module should have no side effects, so the SQLite tables are
created here (on startup) rather than at import time.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.invariants import check_city_coverage
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.services import booking_service, saved_place_service, trip_service
from app.services.flight_service import init_flight_index

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks, yield while the app serves, then shut down."""
    settings = get_settings()
    logger.info("Database URL: %s", settings.database_url)
    engine = get_engine(settings.database_url)
    # SQLite (local/dev/test) self-creates its schema; Postgres schema is
    # managed by Alembic (alembic upgrade head, run by the container entrypoint).
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine, checkfirst=True)

    # Seed the read-only reference entities from app/data BEFORE any check that
    # reads them. Idempotent (merge + City natural-key upsert), so re-runs are
    # safe. On Postgres the schema is already created by Alembic; seeding here
    # populates a fresh DB so the later (Chunk E) DB-backed coverage check has
    # data to read.
    seed_all(get_session_factory(settings.database_url))

    # Enforce the "every city has ≥3 hotels and ≥3 places" promise from
    # CLAUDE.md — a typo in seed data would otherwise only surface when a
    # user searched the affected city.
    check_city_coverage()

    # The per-service init_db() calls (also create_all, idempotent) keep each
    # service constructable/initable independently in tests; on Postgres they
    # are no-ops after Alembic has run (checkfirst=True).
    try:
        booking_service.init_db()
        trip_service.init_db()
        saved_place_service.init_db()
        init_flight_index()
    except Exception:
        logger.exception("Could not initialise database at %s", settings.database_url)
        raise

    logger.info("Startup complete — bookings, trips, and flight-index tables ready")
    yield
    logger.info("Shutting down")
