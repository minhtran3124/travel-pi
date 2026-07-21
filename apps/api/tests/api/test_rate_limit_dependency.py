"""Reusable rate-limit dependency + 429/Retry-After mapping (T3.1)."""

import pytest
from app.core.auth import AuthUser, get_current_user_optional
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.rate_limit import enforce_rate_limit, rate_limit
from app.db.base import Base
from app.db.engine import get_session_factory
from app.db.session import get_session
from app.exceptions import RateLimitError
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def session_factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'rl.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())
    return factory


# --- core callable -------------------------------------------------------


def test_enforce_raises_rate_limit_error_after_limit(session_factory):
    s = session_factory()
    for _ in range(3):
        d = enforce_rate_limit(
            s, name="t", subject="u1", limit=3, window_seconds=60, now_epoch=1000
        )
        assert d.allowed
    with pytest.raises(RateLimitError) as ei:
        enforce_rate_limit(
            s, name="t", subject="u1", limit=3, window_seconds=60, now_epoch=1000
        )
    assert ei.value.status_code == 429
    assert ei.value.retry_after == 20  # reset (1020) - now (1000)


# --- dependency over a throwaway app -------------------------------------


def _client(session_factory, user):
    app = FastAPI()
    register_exception_handlers(app, get_settings())

    @app.post("/rl")
    def route(
        _: None = Depends(rate_limit(name="t", limit=2, window_seconds=60)),
    ) -> dict:
        return {"ok": True}

    def _session_override():
        s = session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return TestClient(app)


def test_dependency_allows_then_429_with_retry_after(session_factory):
    client = _client(
        session_factory, AuthUser(id="u1", email=None, role=None, claims={})
    )
    assert client.post("/rl").status_code == 200
    assert client.post("/rl").status_code == 200
    resp = client.post("/rl")
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") is not None
    assert resp.json()["error"] == "RateLimitError"


def test_dependency_isolates_subjects(session_factory):
    u1 = _client(session_factory, AuthUser(id="u1", email=None, role=None, claims={}))
    u1.post("/rl")
    u1.post("/rl")
    assert u1.post("/rl").status_code == 429
    # A different authed subject on the same DB is unaffected.
    u2 = _client(session_factory, AuthUser(id="u2", email=None, role=None, claims={}))
    assert u2.post("/rl").status_code == 200


def test_dependency_skips_when_no_subject(session_factory):
    # Anonymous with no user_id fallback -> limit skipped (auth layer decides).
    client = _client(session_factory, None)
    for _ in range(5):
        assert client.post("/rl").status_code == 200
