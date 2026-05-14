"""Domain exceptions, decoupled from FastAPI.

Service-layer code raises these instead of ``HTTPException`` so it stays
free of HTTP/web concerns. ``app.main`` registers a single global handler
that turns any :class:`AppError` into the right HTTP response.
"""


class AppError(Exception):
    """Base class for domain errors. Carries the HTTP status to respond with."""

    status_code: int = 500
    default_detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    """A requested resource does not exist (HTTP 404)."""

    status_code = 404
    default_detail = "Resource not found"


class UpstreamError(AppError):
    """A call to an upstream service failed (HTTP 502)."""

    status_code = 502
    default_detail = "Upstream service unavailable"


class CityNotFoundError(NotFoundError):
    """Geocoding could not resolve a city name to coordinates."""


class WeatherUnavailableError(UpstreamError):
    """The upstream Open-Meteo API call failed."""
