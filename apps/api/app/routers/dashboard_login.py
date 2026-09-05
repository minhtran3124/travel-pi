"""Login/logout for the server-rendered dashboard (specs/dashboard-auth-required).

Separate from ``dashboard.py`` so these routes carry no guard dependency —
they must be reachable while logged out.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates

from app.core.dashboard_auth import (
    LOGIN_PATH,
    authenticate,
    clear_session_cookie,
    create_session_token,
    credentials_configured,
    is_already_signed_in,
    safe_next,
    set_session_cookie,
)
from app.routers.tags import Tags

router = APIRouter(prefix="/dashboard", tags=[Tags.dashboard], include_in_schema=False)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/login")
def login_form(
    request: Request,
    already_signed_in: Annotated[bool, Depends(is_already_signed_in)],
    next: str = "/dashboard",
):
    if already_signed_in:
        return RedirectResponse("/dashboard", status_code=303)
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "configured": credentials_configured(),
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    next: str = "/dashboard",
):
    if not credentials_configured():
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Dashboard login is not configured on this server",
                "configured": False,
            },
            status_code=401,
        )
    if authenticate(form.username, form.password):
        response = RedirectResponse(safe_next(next), status_code=303)
        set_session_cookie(response, create_session_token(form.username))
        return response
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": "Invalid username or password",
            "configured": True,
        },
        status_code=401,
    )


@router.post("/logout")
def logout():
    response = RedirectResponse(LOGIN_PATH, status_code=303)
    clear_session_cookie(response)
    return response
