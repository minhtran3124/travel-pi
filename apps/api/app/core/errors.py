"""Exception handlers producing one JSON error envelope for every failure: ``error``, ``message``, ``status_code``, ``path``, and optional ``hint``/``errors``."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.exceptions import AppError, RateLimitError

logger = logging.getLogger(__name__)

# Map by status code so the envelope's ``error`` is self-documenting: an
# unmatched-route ``NotFound`` vs a domain ``NotFoundError``.
_HTTP_ERROR_LABELS = {
    400: "BadRequest",
    401: "Unauthorized",
    403: "Forbidden",
    404: "NotFound",
    405: "MethodNotAllowed",
    409: "Conflict",
    422: "UnprocessableEntity",
    429: "TooManyRequests",
    503: "ServiceUnavailable",
}


def _error_body(
    error: str,
    message: str,
    status_code: int,
    request: Request,
    **extra: object,
) -> dict:
    body: dict = {
        "error": error,
        "message": message,
        "status_code": status_code,
        "path": request.url.path,
    }
    rid = getattr(request.state, "request_id", None)
    if rid:
        body["request_id"] = rid
    return {**body, **extra}


def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    """Register the JSON-envelope exception handlers on the app."""

    # Turn a domain error into an HTTP response so services stay free of FastAPI/HTTP concerns.
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
        # Surface retry_after as the Retry-After header; the policy decision
        # travels via request.state to the middleware for the X-RateLimit-* values.
        headers: dict[str, str] | None = None
        if isinstance(exc, RateLimitError):
            headers = {"Retry-After": str(exc.retry_after)}
            # Mark even a metadata-less 429 as rate-limited so middleware omits nominal capacity headers.
            request.state.rate_limit_applied = True
            if (
                exc.limit is not None
                and exc.remaining is not None
                and exc.reset_at is not None
            ):
                request.state.rate_limit = {
                    "limit": exc.limit,
                    "remaining": exc.remaining,
                    "reset": exc.reset_at,
                }
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                type(exc).__name__, exc.detail, exc.status_code, request, **extra
            ),
            headers=headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        label = _HTTP_ERROR_LABELS.get(exc.status_code, "HTTPException")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(label, str(exc.detail), exc.status_code, request),
            # Forward challenge/hint headers the raiser attached (e.g.
            # ``WWW-Authenticate: Basic``) — the envelope override had dropped them.
            headers=exc.headers,
        )

    # Catch-all so a non-AppError escaping a route still returns the JSON
    # envelope, not Starlette's plaintext 500; details hidden in production.
    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        message = (
            "Internal server error"
            if settings.is_production
            else f"{type(exc).__name__}: {exc}"
        )
        return JSONResponse(
            status_code=500,
            content=_error_body("InternalServerError", message, 500, request),
        )

    # Keep the per-field detail under ``errors`` so callers can pinpoint what to fix.
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
