"""Travel Planner Mock API — application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000/docs for the Swagger UI.
"""

import logging

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logging import configure_logging
from app.core.middleware import register_middleware
from app.routers.main import router as api_router

logger = logging.getLogger(__name__)


def _operation_id(route: APIRoute) -> str:
    """Stable operationId = the handler function name (survives refactors)."""
    return route.name


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
        generate_unique_id_function=_operation_id,
        **docs_kwargs,
    )

    register_exception_handlers(app, settings)
    register_middleware(app, settings)
    app.include_router(api_router)

    # Fail fast on duplicate operationIds — a duplicate handler name silently
    # breaks TS codegen, so surface it at startup rather than only in CI. Only
    # schema-visible routes reach codegen; include_in_schema=False routes (e.g.
    # the dashboard page served at both "" and "/") are intentionally exempt.
    ids = [
        r.operation_id or r.name
        for r in app.routes
        if isinstance(r, APIRoute) and r.include_in_schema
    ]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise RuntimeError(
            f"Duplicate operationIds (breaks TS codegen): {sorted(dupes)}"
        )

    return app


app = create_app()
