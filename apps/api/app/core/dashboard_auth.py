"""Access guard for the server-rendered ``/dashboard/*`` operator pages: HTTP Basic when credentials are set, else open in development but 404 in production."""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.exceptions import NotFoundError

# auto_error=False so a missing header reaches us as ``None`` and we choose the failure mode.
_basic = HTTPBasic(auto_error=False)


def require_dashboard_access(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> None:
    """Authorize a request to a ``/dashboard/*`` page (401 when Basic auth fails, 404 in production when no credentials are set)."""
    settings = get_settings()
    user = settings.dashboard_basic_user
    password = settings.dashboard_basic_password

    if user and password:
        ok = credentials is not None
        if ok:
            # compare_digest raises TypeError on non-ASCII input; a malformed
            # credential must read as wrong (401), never a 500.
            try:
                ok = secrets.compare_digest(
                    credentials.username, user
                ) and secrets.compare_digest(credentials.password, password)
            except TypeError:
                ok = False
        if not ok:
            # Starlette's HTTPException carries the challenge header through, so the browser prompts.
            raise StarletteHTTPException(
                status_code=401,
                detail="Dashboard authentication required.",
                headers={"WWW-Authenticate": "Basic"},
            )
        return

    if settings.is_production:
        raise NotFoundError("Not found")

    # Development with no credentials configured: leave the dashboard open.
    return
