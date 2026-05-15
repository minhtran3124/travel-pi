"""The error envelope schema + an OpenAPI ``responses`` helper.

Every failed request — domain (``AppError``), HTTP, or request-validation —
comes back in the one envelope produced by the handlers in ``app.main``.
This module documents that shape so Swagger renders error responses
correctly instead of showing them as "Undocumented" (or, for 422, with the
stale default ``HTTPValidationError`` shape).
"""

from typing import Any

from app.schemas.base import AppBaseModel


class ErrorResponse(AppBaseModel):
    """The consistent JSON envelope returned by every failed request."""

    error: str  # Exception/class name, e.g. "NotFoundError", "ValidationError"
    message: str
    status_code: int
    path: str
    errors: list[dict[str, Any]] | None = None  # Per-field detail (422 only)


# Human-readable description per status code, for the OpenAPI docs.
_DESCRIPTIONS: dict[int, str] = {
    404: "Resource not found",
    409: "Request conflicts with the current state",
    422: "Request validation failed",
    502: "Upstream service unavailable",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Build an OpenAPI ``responses=`` map for the given error status codes.

    Pass this to a route decorator so Swagger documents each error with the
    real :class:`ErrorResponse` shape, e.g.
    ``responses=error_responses(404, 422)``.
    """
    return {
        code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]}
        for code in status_codes
    }
