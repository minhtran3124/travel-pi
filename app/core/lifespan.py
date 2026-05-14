"""Application lifespan — startup and shutdown hooks.

Importing a module should have no side effects, so the bookings table is
created here (on startup) rather than at import time.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.booking_service import get_booking_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks, yield while the app serves, then shut down."""
    get_booking_service().init_db()
    logger.info("Startup complete — bookings table ready")
    yield
    logger.info("Shutting down")
