"""Exception handlers — the single JSON error envelope (kept FastAPI-side).

Every error — domain, HTTP, or request-validation — leaves the API in the same
JSON envelope, so an agent consuming the API can parse failures the same way
regardless of where they originated::

    {"error": <class>, "message": <str>, "status_code": <int>,
     "path": <str>, "hint": <str>?, "errors": [...]?}

``hint`` is an optional, machine-actionable recovery suggestion for the caller —
what to try next. See ``app.exceptions.AppError``.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.exceptions import AppError, RateLimitError

logger = logging.getLogger(__name__)

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
    """Register the JSON-envelope exception handlers on the app.

    :param app: The FastAPI app to register handlers on.
    :param settings: Application settings, used to decide whether unexpected-error
        details are hidden in production.
    """

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
        # RateLimitError carries a retry_after; surface it as the Retry-After
        # header so clients back off correctly. Its policy decision also travels
        # through request.state to the outer middleware, which emits truthful
        # X-RateLimit-* values after this response is built.
        headers: dict[str, str] | None = None
        if isinstance(exc, RateLimitError):
            headers = {"Retry-After": str(exc.retry_after)}
            # Mark even a manually raised/metadata-less 429 as rate-limited so
            # middleware does not add unrelated nominal capacity headers.
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
        )

    # Catch-all for any non-AppError exception that escapes a route. Without
    # this, Starlette's ServerErrorMiddleware returns a plaintext
    # "Internal Server Error", breaking the JSON-envelope contract. In
    # production the exception detail is hidden to avoid leaking internals.
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
