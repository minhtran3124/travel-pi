"""Classify LLM-provider failures into a stable code plus a client-safe message.

Raw provider errors carry request ids, key fragments and setup hints, so they are logged server-side and never forwarded to clients.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderFailure:
    """A recognised provider failure: ``code`` is the SSE/API error code, ``message`` is safe to show."""

    code: str
    message: str


_AUTH = ProviderFailure(
    "llm_auth",
    "The AI provider rejected the server's credentials. Please contact the administrator.",
)
_UNAVAILABLE = ProviderFailure(
    "llm_unavailable",
    "The AI provider is temporarily unavailable or over its quota. Please try again later.",
)

_AUTH_NAMES = {"AuthenticationError", "PermissionDeniedError"}
_UNAVAILABLE_NAMES = {
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "OverloadedError",
}
# A missing key surfaces as a plain TypeError/ValueError from the SDK, so match its wording.
_AUTH_MARKERS = (
    "could not resolve authentication method",
    "api_key client option must be set",
    "invalid x-api-key",
    "incorrect api key",
    "authentication_error",
)


def classify_provider_error(exc: BaseException) -> ProviderFailure | None:
    """Return the failure class for a provider auth/availability error, or ``None`` for anything else."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _AUTH_NAMES:
            return _AUTH
        if cls.__name__ in _UNAVAILABLE_NAMES:
            return _UNAVAILABLE
    text = str(exc).lower()
    if any(marker in text for marker in _AUTH_MARKERS):
        return _AUTH
    return None
