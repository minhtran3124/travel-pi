"""Application lifespan — startup and shutdown hooks.

Importing a module should have no side effects, so the SQLite tables are
created here (on startup) rather than at import time.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.invariants import check_city_coverage
from app.services.booking_service import get_booking_service
from app.services.flight_service import init_flight_index
from app.services.trip_service import get_trip_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks, yield while the app serves, then shut down."""
    # Resolve the configured DB path to an absolute one and log it. The
    # default is CWD-relative — logging the resolved path turns the next
    # "where did my bookings go?" debugging session into a one-line answer.
    db_path = Path(get_settings().database_path).resolve()
    logger.info("SQLite database resolved to %s", db_path)

    # Enforce the "every city has ≥3 hotels and ≥3 places" promise from
    # CLAUDE.md — a typo in seed data would otherwise only surface when a
    # user searched the affected city.
    check_city_coverage()

    # Wrap init so a write/permission failure surfaces with the path that
    # caused it, instead of an opaque ``sqlite3.OperationalError`` traceback
    # at boot.
    try:
        get_booking_service().init_db()
        get_trip_service().init_db()
        init_flight_index()
    except Exception:
        logger.exception("Could not initialise SQLite database at %s", db_path)
        raise

    logger.info("Startup complete — bookings, trips, and flight-index tables ready")
    yield
    logger.info("Shutting down")
