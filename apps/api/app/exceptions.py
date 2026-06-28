"""Domain exceptions, decoupled from FastAPI.

Service-layer code raises these instead of ``HTTPException`` so it stays
free of HTTP/web concerns. ``app.main`` registers a single global handler
that turns any :class:`AppError` into the right HTTP response.
"""


class AppError(Exception):
    """Base class for domain errors. Carries the HTTP status to respond with.

    An optional ``hint`` field gives the caller — typically an LLM agent —
    a concrete recovery suggestion ("call X to find valid IDs", "try
    different dates"). It is surfaced in the error envelope so the agent
    can act on it without parsing the human-readable ``message``.
    """

    status_code: int = 500
    default_detail: str = "Internal server error"

    def __init__(self, detail: str | None = None, *, hint: str | None = None) -> None:
        self.detail = detail or self.default_detail
        self.hint = hint
        super().__init__(self.detail)


class AuthError(AppError):
    """Authentication failed — missing or invalid credentials (HTTP 401).

    Raised when a Supabase access token is absent, malformed, or fails
    signature/issuer/audience/expiry verification. See ``app.core.auth``.
    """

    status_code = 401
    default_detail = "Authentication required"


class NotFoundError(AppError):
    """A requested resource does not exist (HTTP 404)."""

    status_code = 404
    default_detail = "Resource not found"


class ConflictError(AppError):
    """The request cannot be fulfilled in the current state (HTTP 409).

    Used e.g. when a hotel has no rooms available for the requested dates.
    """

    status_code = 409
    default_detail = "Request conflicts with the current state"


class DomainValidationError(AppError):
    """A request is well-formed but semantically invalid (HTTP 422).

    For value-level checks the service layer makes that Pydantic cannot express
    on the request schema alone (e.g. an enum-like field constrained to a small
    set). Renders in the same envelope as request-validation 422s.
    """

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
    """The caller is authenticated but lacks the required role/permission (HTTP 403).

    Raised when a valid token is present but the user does not hold the role
    required to perform the action (e.g. ``role != "admin"``).
    """

    status_code = 403
    default_detail = "Forbidden"


class QuotaExceededError(AppError):
    """The user has exceeded their daily usage quota (HTTP 429).

    Raised by ``app.services.quota_service`` when a free-tier user's turn count
    for the current UTC day meets or exceeds the configured daily limit. The
    ``AppError`` handler in ``app.core.errors`` maps this to 429 automatically.
    """

    status_code = 429
    default_detail = (
        "Daily message limit reached. Upgrade to premium for unlimited access."
    )
