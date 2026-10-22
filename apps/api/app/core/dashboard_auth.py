"""Cookie session for the server-rendered ``/dashboard/*`` pages.

The dashboard is an operator surface (agent-config edits, the bookings ledger,
the command-palette index). Every dashboard route requires a login
(specs/dashboard-auth-required, D1): ``POST /dashboard/login`` checks the
configured user/password and sets an ``HttpOnly`` cookie holding a short
``HS256`` JWT (``sub``, ``iat``, ``exp``) signed with ``DASHBOARD_SECRET_KEY``
(D2/D3). :func:`get_current_dashboard_user` is the router-level guard; it
raises :class:`DashboardLoginRequired`, whose handler in ``app.core.errors``
redirects HTML requests to the login page and answers JSON otherwise (D5).

"Configured" means all three env vars are set and the secret is at least
32 bytes (D4). Every settings read for this feature goes through this
module's ``get_settings`` so tests patch one seam (D10).
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import jwt
from fastapi import Depends, Request, Response
from fastapi.security import APIKeyCookie

from app.core.config import get_settings
from app.exceptions import AuthError

SESSION_COOKIE = "dashboard_session"
SESSION_TTL = timedelta(hours=12)
LOGIN_PATH = "/dashboard/login"
_ALGORITHM = "HS256"
# PyJWT 2.13 warns (InsecureKeyLengthWarning) for HMAC keys shorter than this.
_MIN_SECRET_BYTES = 32

# ``auto_error=False`` so a missing cookie reaches the guard as ``None`` rather
# than short-circuiting to a 403 — we decide the failure mode ourselves.
_cookie_scheme = APIKeyCookie(
    name=SESSION_COOKIE, scheme_name="dashboardSession", auto_error=False
)


@dataclass(frozen=True)
class DashboardUser:
    """The operator behind a verified dashboard session cookie."""

    username: str


class DashboardLoginRequired(AuthError):
    """No valid dashboard session — the handler redirects HTML requests to login."""

    default_detail = "Dashboard login required"


def missing_credentials() -> list[str]:
    """Names of the dashboard env vars that are unset (or, for the secret, too short)."""
    settings = get_settings()
    missing = []
    if not settings.dashboard_basic_user:
        missing.append("DASHBOARD_BASIC_USER")
    if not settings.dashboard_basic_password:
        missing.append("DASHBOARD_BASIC_PASSWORD")
    secret = settings.dashboard_secret_key or ""
    if len(secret.encode()) < _MIN_SECRET_BYTES:
        missing.append("DASHBOARD_SECRET_KEY")
    return missing


def credentials_configured() -> bool:
    """True when user, password and a ≥32-byte secret are all set (D4)."""
    return not missing_credentials()


def authenticate(username: str, password: str) -> bool:
    """Constant-time check of a login form against the configured pair."""
    if not credentials_configured():
        return False
    settings = get_settings()
    # ``secrets.compare_digest`` raises TypeError on non-ASCII str input; a
    # malformed credential must read as "wrong", never a 500.
    try:
        username_ok = secrets.compare_digest(username, settings.dashboard_basic_user)
        password_ok = secrets.compare_digest(
            password, settings.dashboard_basic_password
        )
        return username_ok and password_ok
    except TypeError:
        return False


def create_session_token(username: str, now: datetime | None = None) -> str:
    """Issue the session JWT for ``username`` (``exp`` = ``iat`` + 12 h).

    :raises DashboardLoginRequired: when credentials are not configured, so a
        weak or missing secret never reaches ``jwt.encode``.
    """
    if not credentials_configured():
        raise DashboardLoginRequired("Dashboard login is not configured.")
    issued = now or datetime.now(UTC)
    claims = {"sub": username, "iat": issued, "exp": issued + SESSION_TTL}
    return jwt.encode(claims, get_settings().dashboard_secret_key, algorithm=_ALGORITHM)


def get_current_dashboard_user(
    token: Annotated[str | None, Depends(_cookie_scheme)],
) -> DashboardUser:
    """Router-level guard: verify the session cookie or raise :class:`DashboardLoginRequired`.

    :param token: The ``dashboard_session`` cookie value, or ``None`` when absent.
    :raises DashboardLoginRequired: when the cookie is missing, credentials are
        not configured, the token fails verification (signature, ``exp``,
        future ``iat``, missing claims, wrong ``alg``), or ``sub`` is not the
        configured user.
    """
    if token is None or not credentials_configured():
        raise DashboardLoginRequired()
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.dashboard_secret_key,
            algorithms=[_ALGORITHM],
            leeway=60,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise DashboardLoginRequired() from exc
    if claims["sub"] != settings.dashboard_basic_user:
        raise DashboardLoginRequired()
    return DashboardUser(username=claims["sub"])


def is_already_signed_in(
    token: Annotated[str | None, Depends(_cookie_scheme)],
) -> bool:
    """Optional-auth variant of :func:`get_current_dashboard_user` for the login page.

    Unlike the router guard, a missing/invalid session is not an error here — it
    just means "show the login form" rather than "redirect to it".
    """
    try:
        get_current_dashboard_user(token)
    except DashboardLoginRequired:
        return False
    return True


def safe_next(value: str | None) -> str:
    """Return ``value`` only when it is a same-site dashboard path (D6), else ``/dashboard``.

    ``startswith("/dashboard")`` already rejects ``//host`` and absolute URLs;
    CR/LF are refused so the value can never smuggle a header; the login page
    itself is refused so a login never redirects back to the form.
    """
    if (
        not value
        or not value.startswith("/dashboard")
        or "\r" in value
        or "\n" in value
        or value == LOGIN_PATH
        or value.startswith(LOGIN_PATH + "?")
    ):
        return "/dashboard"
    return value


def login_redirect_url(request: Request) -> str:
    """The login URL carrying the request's path + query as ``next`` (URL-encoded)."""
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return f"{LOGIN_PATH}?{urlencode({'next': target})}"


def _cookie_flags() -> dict:
    return {
        "path": "/dashboard",
        "httponly": True,
        "samesite": "lax",
        "secure": get_settings().is_production,
    }


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session cookie with the D3 attributes."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        **_cookie_flags(),
    )


def clear_session_cookie(response: Response) -> None:
    """Expire the session cookie — same path and flags as set, or browsers keep it."""
    response.delete_cookie(SESSION_COOKIE, **_cookie_flags())
