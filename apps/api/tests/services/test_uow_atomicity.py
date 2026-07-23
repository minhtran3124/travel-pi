"""Unit-of-work atomicity (specs/di-session-refactor, wave 3).

The request-scoped get_session dependency commits when the handler returns and
rolls back when it raises — so a multi-step write that fails partway leaves the
database untouched. This drives the real seam through FastAPI.
"""

from typing import Annotated

import pytest
from app.core.config import get_settings
from app.db import session as session_module
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def uow_app(tmp_path, monkeypatch):
    """A tiny app whose get_session points at a temp DB with a scratch table."""
    url = f"sqlite:///{tmp_path / 'uow.db'}"
    settings = get_settings()
    object.__setattr__(settings, "database_url", url)
    monkeypatch.setattr(session_module, "get_settings", lambda: settings)

    engine = get_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))

    app = FastAPI()

    @app.post("/write-then-fail")
    def write_then_fail(session: Annotated[Session, Depends(get_session)]):
        session.execute(text("INSERT INTO t (v) VALUES ('partial')"))
        raise RuntimeError("boom after write")

    @app.post("/write-ok")
    def write_ok(session: Annotated[Session, Depends(get_session)]):
        session.execute(text("INSERT INTO t (v) VALUES ('kept')"))
        return {"ok": True}

    return url, app


def _count(url: str) -> int:
    with get_session_factory(url)() as s:
        return s.execute(text("SELECT COUNT(*) FROM t")).scalar()


def test_handler_failure_rolls_back_the_write(uow_app):
    url, app = uow_app
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/write-then-fail")

    assert resp.status_code == 500
    assert _count(url) == 0  # the partial write was rolled back


def test_handler_success_commits_the_write(uow_app):
    url, app = uow_app
    client = TestClient(app)

    assert client.post("/write-ok").status_code == 200
    assert _count(url) == 1  # committed at the request boundary
