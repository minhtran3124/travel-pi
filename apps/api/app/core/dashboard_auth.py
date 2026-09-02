"""Access guard for the server-rendered ``/dashboard/*`` pages.

The dashboard is an operator surface (agent-config edits, the bookings ledger,
the command-palette index). It carries no auth of its own, so this dependency
gates every dashboard route:

- **Credentials configured** (``dashboard_basic_user`` *and*
  ``dashboard_basic_password`` set): require HTTP Basic. Both fields are
  compared with :func:`secrets.compare_digest` (constant-time); a missing or
  mismatched credential yields ``401`` with a ``WWW-Authenticate: Basic``
  challenge so a browser prompts for login.
- **No credentials, production**: the pages must not be reachable, so return
  ``404`` (the same "does not exist" answer an unknown route gives — it does
  not advertise that a guarded surface is here).
- **No credentials, development**: open, so local dev stays zero-config.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.exceptions import NotFoundError

# ``auto_error=False`` so a missing Authorization header reaches us as ``None``
# rather than short-circuiting to a 403 — we decide the failure mode ourselves.
_basic = HTTPBasic(auto_error=False)


def require_dashboard_access(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> None:
    """Authorize a request to a ``/dashboard/*`` page.

    :param request: The incoming request (unused today; kept so the guard can
        grow request-aware policy without a signature change).
    :param credentials: Parsed HTTP Basic credentials, or ``None`` when absent.
    :raises StarletteHTTPException: ``401`` when Basic auth is required but the
        credentials are absent or wrong.
    :raises NotFoundError: ``404`` in production when no credentials are set.
    """
    settings = get_settings()
    user = settings.dashboard_basic_user
    password = settings.dashboard_basic_password

    if user and password:
        if credentials is None or not (
            secrets.compare_digest(credentials.username, user)
            and secrets.compare_digest(credentials.password, password)
        ):
            # Starlette's HTTPException carries the challenge header straight
            # through the ASGI exception middleware, so the browser prompts.
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
