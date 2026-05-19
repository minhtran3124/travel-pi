"""Travel Planner Mock API — application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://localhost:8000/docs for the Swagger UI.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings, get_settings
from app.core.lifespan import lifespan
from app.core.logging import configure_logging
from app.exceptions import AppError
from app.routers.main import router as api_router

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

    # Every error — domain, HTTP, or request-validation — leaves the API in
    # the same JSON envelope, so an agent consuming the API can parse failures
    # the same way regardless of where they originated:
    #   {"error": <class>, "message": <str>, "status_code": <int>,
    #    "path": <str>, "hint": <str>?, "errors": [...]?}
    # ``hint`` is an optional, machine-actionable recovery suggestion for the
    # caller — what to try next. See ``app.exceptions.AppError``.
    def _error_body(
        error: str,
        message: str,
        status_code: int,
        request: Request,
        **extra: object,
    ) -> dict:
        return {
            "error": error,
            "message": message,
            "status_code": status_code,
            "path": request.url.path,
            **extra,
        }

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
        extra: dict[str, object] = {}
        if exc.hint:
            extra["hint"] = exc.hint
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                type(exc).__name__, exc.detail, exc.status_code, request, **extra
            ),
        )

    # HTTPException covers both routers that raise it directly (e.g. a bad
    # date → 422) and Starlette's own 404/405 for unmatched routes. Map by
    # status code so the envelope's ``error`` field is self-documenting —
    # an unmatched route's ``"NotFound"`` is then distinguishable from a
    # domain ``"NotFoundError"`` raised by the service layer.
    _HTTP_ERROR_LABELS = {
        400: "BadRequest",
        401: "Unauthorized",
        403: "Forbidden",
        404: "NotFound",
        405: "MethodNotAllowed",
        409: "Conflict",
        422: "UnprocessableEntity",
        429: "TooManyRequests",
    }

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        label = _HTTP_ERROR_LABELS.get(exc.status_code, "HTTPException")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                label, str(exc.detail), exc.status_code, request
            ),
        )

    # Pydantic request-validation failures (422) — keep the per-field detail
    # under ``errors`` so callers can pinpoint what to fix.
    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "ValidationError",
                "Request validation failed",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                request,
                hint=(
                    "Inspect the 'errors' array for per-field problems "
                    "(each entry has 'loc', 'msg', and 'type'). Fix the "
                    "listed fields and retry."
                ),
                errors=jsonable_encoder(exc.errors()),
            ),
        )

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

    # Register every endpoint group via the aggregate router.
    app.include_router(api_router)

    return app


app = create_app()
