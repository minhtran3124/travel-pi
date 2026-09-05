"""SC-8: ``login.html`` and the ``base.html`` logout form compile and carry the
inputs the dashboard-auth routes depend on.

Renders the templates directly through Jinja — never through the app — so this
module stays independent of the auth dependency and router wiring.
"""

from pathlib import Path
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "app" / "templates"
_TEMPLATES = Jinja2Templates(directory=str(_TEMPLATE_DIR))
_NOT_CONFIGURED = "Dashboard login is not configured on this server"


def _render_login(**overrides: object) -> str:
    context = {
        "request": SimpleNamespace(
            url=SimpleNamespace(path="/dashboard/login", query="next=%2Fdashboard")
        ),
        "error": None,
        "configured": True,
    }
    context.update(overrides)
    return _TEMPLATES.get_template("login.html").render(**context)


def test_login_page_has_post_form_with_credential_inputs():
    html = _render_login()

    assert 'method="post"' in html
    assert 'action="/dashboard/login?next=%2Fdashboard"' in html
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert _NOT_CONFIGURED not in html
    assert '<button type="submit" class="tab">Log in</button>' in html


def test_login_page_is_standalone():
    source = (_TEMPLATE_DIR / "login.html").read_text()

    assert "{% extends" not in source


def test_login_page_renders_error_when_set():
    html = _render_login(error="Invalid username or password")

    assert "Invalid username or password" in html


def test_login_page_unconfigured_shows_notice_and_disables_submit():
    html = _render_login(configured=False)

    assert _NOT_CONFIGURED in html
    assert '<button type="submit" class="tab" disabled>Log in</button>' in html


def test_base_template_has_logout_form():
    source = (_TEMPLATE_DIR / "base.html").read_text()

    assert 'action="/dashboard/logout"' in source
    assert 'method="post"' in source
