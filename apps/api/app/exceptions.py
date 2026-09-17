"""Domain exceptions, decoupled from FastAPI — a global handler maps any :class:`AppError` to its HTTP response."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.schemas.booking import Booking


class AppError(Exception):
    """Base class for domain errors; the optional ``hint`` gives an agent a machine-actionable recovery suggestion in the envelope."""

    status_code: int = 500
    default_detail: str = "Internal server error"

    def __init__(self, detail: str | None = None, *, hint: str | None = None) -> None:
        self.detail = detail or self.default_detail
        self.hint = hint
        super().__init__(self.detail)


class AuthError(AppError):
    """Authentication failed — missing or invalid credentials (HTTP 401)."""

    status_code = 401
    default_detail = "Authentication required"


class NotFoundError(AppError):
    """A requested resource does not exist (HTTP 404)."""

    status_code = 404
    default_detail = "Resource not found"


class ConflictError(AppError):
    """The request cannot be fulfilled in the current state (HTTP 409)."""

    status_code = 409
    default_detail = "Request conflicts with the current state"


#: Stable tag in a :class:`DuplicateBookingError` detail so a duplicate warning is machine-detectable rather than free-text matched; the bare form is the fail-safe wildcard.
DUPLICATE_WARNING_MARKER = "[possible-duplicate]"

#: Group 1 is the raw id (bare/legacy marker -> ``None``); anything but a clean id is treated as the wildcard, so a malformed marker fails safe.
DUPLICATE_WARNING_MARKER_RE = re.compile(r"\[possible-duplicate(?::([^\]]*))?\]")


def duplicate_warning_marker(booking_id: str) -> str:
    """Marker embedding the existing booking's id, e.g. ``[possible-duplicate:<id>]``."""
    return f"[possible-duplicate:{booking_id}]"


class DuplicateBookingError(ConflictError):
    """A prior active booking already matches this request (HTTP 409); raised only when a caller opts in with ``check_duplicate=True``. The detail always carries an id-bearing :func:`duplicate_warning_marker` tag."""

    default_detail = "A matching booking already exists."

    def __init__(
        self,
        detail: str | None = None,
        *,
        existing: Booking,
        matches: Sequence[Booking] | None = None,
        hint: str | None = None,
    ) -> None:
        detail = detail or self.default_detail
        if DUPLICATE_WARNING_MARKER_RE.search(detail) is None:
            detail = f"{detail} {duplicate_warning_marker(existing.id)}"
        super().__init__(detail, hint=hint)
        #: The already-stored booking this request duplicates (the newest match).
        self.existing = existing
        #: Every active booking that matched, so a same-turn override is refused if any was flagged.
        self.matches = tuple(matches) if matches is not None else (existing,)


class DomainValidationError(AppError):
    """A request is well-formed but semantically invalid (HTTP 422) — for value-level checks Pydantic cannot express on the schema alone."""

    status_code = 422
    default_detail = "Request validation failed"


class UpstreamError(AppError):
    """A call to an upstream service failed (HTTP 502)."""

    status_code = 502
    default_detail = "Upstream service unavailable"


class CityNotFoundError(NotFoundError):
    """Geocoding could not resolve a city name to coordinates."""


class WeatherUnavailableError(UpstreamError):
    """The upstream Open-Meteo API call failed."""


class RoutingUnavailableError(UpstreamError):
    """The upstream OpenRouteService API call failed."""


class ForbiddenError(AppError):
    """The caller is authenticated but lacks the required role/permission (HTTP 403)."""

    status_code = 403
    default_detail = "Forbidden"


class PremiumRequiredError(ForbiddenError):
    """The caller's tier does not permit this action (HTTP 403)."""

    default_detail = "This action requires a premium account."


class QuotaExceededError(AppError):
    """The user has exceeded their daily usage quota (HTTP 429)."""

    status_code = 429
    default_detail = (
        "Daily message limit reached. Upgrade to premium for unlimited access."
    )


class RateLimitError(AppError):
    """A caller exceeded a short-window abuse rate limit (HTTP 429), distinct from the per-day :class:`QuotaExceededError`; ``retry_after`` seconds becomes the ``Retry-After`` header."""

    status_code = 429
    default_detail = "Rate limit exceeded. Please retry shortly."

    def __init__(
        self,
        detail: str | None = None,
        *,
        retry_after: int,
        limit: int | None = None,
        remaining: int | None = None,
        reset_at: int | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(detail, hint=hint)
        self.retry_after = retry_after
        # Policy metadata is optional so manual construction stays backwards compatible; the limiter always supplies all three.
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
