"""Application lifespan — startup and shutdown hooks.

Importing a module should have no side effects, so the SQLite tables are
created here (on startup) rather than at import time.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.booking_service import get_booking_service
from app.services.flight_service import init_flight_index

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks, yield while the app serves, then shut down."""
    get_booking_service().init_db()
    init_flight_index()
    logger.info("Startup complete — bookings and flight-index tables ready")
    yield
    logger.info("Shutting down")
