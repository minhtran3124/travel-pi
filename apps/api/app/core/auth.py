"""Supabase JWT verification (specs/supabase-auth).

A FastAPI dependency that authenticates a request by verifying the Bearer
access token issued by Supabase Auth against the project's JWKS endpoint
(asymmetric RS256/ES256 keys). Following the project DI convention
(``app.db.session.get_session``), routers take ``get_current_user`` via
``Depends`` and tests override it through ``app.dependency_overrides`` — no
module-level singleton, mirroring the di-session pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from app.core.config import get_settings
from app.exceptions import AuthError

logger = logging.getLogger(__name__)

# Supabase signs with RS256 (and ES256 on some projects); accept both so the
# dependency works regardless of the project's configured signing algorithm.
_ALGORITHMS = ["RS256", "ES256"]

# One PyJWKClient per JWKS URL, cached at module scope. PyJWKClient caches the
# fetched signing keys internally, so reusing it avoids refetching per request.
_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(url: str) -> PyJWKClient:
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(url)
        _jwks_clients[url] = client
    return client


@dataclass(frozen=True)
class AuthUser:
    """The authenticated principal extracted from a verified Supabase token."""

    id: str  # the Supabase user id (``sub`` claim)
    email: str | None
    # App-level role sourced from ``app_metadata.role`` (admin-controlled, not
    # user-editable), NOT the top-level ``role`` claim — which Supabase always
    # sets to the Postgres role (``authenticated``/``anon``/``service_role``)
    # and so can never identify an application admin. ``"admin"`` here gates
    # privileged endpoints (e.g. PATCH /admin/users/{id}/tier).
    role: str | None
    claims: dict


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.lower().startswith("bearer "):
        raise AuthError(
            "Missing or malformed Authorization header.",
            hint="Send 'Authorization: Bearer <supabase access token>'.",
        )
    token = header[7:].strip()
    if not token:
        raise AuthError("Empty bearer token.")
    return token


def _verify_bearer_token(request: Request, settings) -> AuthUser:
    """Verify a Bearer token and return the AuthUser. Raises AuthError on any failure."""
    jwks_url = settings.resolved_jwks_url
    if not jwks_url:
        raise AuthError(
            "Supabase auth is not configured.",
            hint="Set SUPABASE_PROJECT_REF or SUPABASE_URL on the API.",
        )

    token = _extract_bearer_token(request)
    try:
        signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
            issuer=settings.resolved_jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        # Never log the token; the exception type is enough to diagnose.
        logger.warning("JWT verification failed: %s", type(exc).__name__)
        raise AuthError("Invalid or expired token.") from exc

    sub = claims.get("sub")
    if not sub:
        raise AuthError("Token missing subject (sub) claim.")
    app_metadata = claims.get("app_metadata") or {}
    return AuthUser(
        id=sub,
        email=claims.get("email"),
        role=app_metadata.get("role"),
        claims=claims,
    )


def get_current_user(request: Request) -> AuthUser:
    """Authenticate the request via its Supabase Bearer token.

    Raises :class:`AuthError` (HTTP 401) when the token is missing, malformed,
    or fails signature / issuer / audience / expiry verification.
    """
    return _verify_bearer_token(request, get_settings())


def get_current_user_optional(request: Request) -> AuthUser | None:
    """Return an :class:`AuthUser` when a valid Bearer token is present, else ``None``.

    Never raises or returns 401 — missing, malformed, or expired tokens all
    yield ``None`` so callers can implement hybrid auth (authed vs anonymous).
    """
    if not request.headers.get("Authorization"):
        return None
    try:
        return _verify_bearer_token(request, get_settings())
    except Exception:
        # Invalid / expired / misconfigured — treat as anonymous.
        return None


# Routers depend on these; tests override via ``app.dependency_overrides``.
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]
OptionalUserDep = Annotated[AuthUser | None, Depends(get_current_user_optional)]
