"""Travel Planner Mock API — application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000/docs for the Swagger UI.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.lifespan import lifespan
from app.core.logging import configure_logging
from app.exceptions import AppError
from app.routers import (
    airports,
    bookings,
    cities,
    dashboard,
    flights,
    hotels,
    meta,
    places,
    tips,
    weather,
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings: Settings = get_settings()
    configure_logging(settings)

    # Hide the interactive docs and raw schema in production — a FastAPI
    # best practice. In development (and tests) they stay on.
    docs_kwargs = (
        {"docs_url": None, "redoc_url": None, "openapi_url": None}
        if settings.is_production
        else {}
    )

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
        **docs_kwargs,
    )

    # Turn any domain error raised by the service layer into an HTTP response,
    # so services stay free of FastAPI/HTTP concerns.
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "%s on %s %s: %s",
            type(exc).__name__,
            request.method,
            request.url.path,
            exc.detail,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # Log one line per request: method, path, status, and how long it took.
    # This is the single source of access logs (Uvicorn's is silenced in
    # app.core.logging), so it works the same however the app is launched.
    @app.middleware("http")
    async def _log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    # CORS — wide open for local dev so the FE/agent can call from anywhere.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )

    # Register routers. Order is cosmetic — it sets the Swagger tag order.
    app.include_router(meta.router)
    app.include_router(airports.router)
    app.include_router(cities.router)
    app.include_router(flights.router)
    app.include_router(hotels.router)
    app.include_router(places.router)
    app.include_router(tips.router)
    app.include_router(weather.router)
    app.include_router(bookings.router)
    # Server-rendered HTML dashboard — excluded from the OpenAPI schema.
    app.include_router(dashboard.router)

    return app


app = create_app()
