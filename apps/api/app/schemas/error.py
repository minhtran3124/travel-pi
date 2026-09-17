"""The error envelope schema + an OpenAPI ``responses`` helper."""

from typing import Any

from pydantic import Field

from app.schemas.base import AppBaseModel


class ErrorResponse(AppBaseModel):
    """The consistent JSON envelope returned by every failed request."""

    error: str = Field(
        description="Exception class name (e.g. 'NotFoundError', 'ValidationError').",
        examples=["NotFoundError"],
    )
    message: str = Field(
        description="Human-readable description of what went wrong.",
        examples=["No flight 'VN123' on HAN→SGN on 2026-06-01"],
    )
    status_code: int = Field(description="HTTP status code.", examples=[404])
    path: str = Field(
        description="The request path that failed.", examples=["/flights/book"]
    )
    hint: str | None = Field(
        default=None,
        description=(
            "Optional recovery suggestion the client (e.g. an LLM agent) "
            "can act on without parsing the message — what to try next."
        ),
        examples=[
            "Use GET /flights/search with origin, destination, and "
            "departure_date to find a valid flight_number."
        ],
    )
    errors: list[dict[str, Any]] | None = Field(
        default=None,
        description="Per-field validation detail (populated for 422 only).",
    )


_DESCRIPTIONS: dict[int, str] = {
    401: "Authentication required",
    403: "Forbidden",
    404: "Resource not found",
    409: "Request conflicts with the current state",
    422: "Request validation failed",
    502: "Upstream service unavailable",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Build an OpenAPI ``responses=`` map for the given error status codes."""
    return {
        code: {"model": ErrorResponse, "description": _DESCRIPTIONS[code]}
        for code in status_codes
    }
