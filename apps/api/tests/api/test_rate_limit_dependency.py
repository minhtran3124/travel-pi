"""Reusable rate-limit dependency + 429/Retry-After mapping (T3.1)."""

import time
from types import SimpleNamespace
from typing import Annotated

import pytest
from app.core import rate_limit as rate_limit_module
from app.core.auth import AuthUser, get_current_user_optional
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.middleware import register_middleware
from app.core.rate_limit import enforce_rate_limit, rate_limit
from app.db import models
from app.db.base import Base
from app.db.engine import get_session_factory
from app.db.session import get_session
from app.exceptions import RateLimitError
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_TestSessionDep = Annotated[Session, Depends(get_session)]

_WINDOW = 60


@pytest.fixture(autouse=True)
def _frozen_limiter_clock(monkeypatch):
    """Pin the limiter's clock mid-window for the whole module.

    The counter is a FIXED window aligned to the wall clock (``now - now %
    window`` in ``RateLimitRepository.hit``), so a test that spends several
    requests on one budget resets that budget if it straddles a window
    boundary — the 429 assertions then see a fresh 200. Tests that pass an
    explicit ``now_epoch`` are unaffected; this only pins the default.
    """
    frozen = (int(time.time()) // _WINDOW) * _WINDOW + _WINDOW // 2
    monkeypatch.setattr(
        rate_limit_module, "time", SimpleNamespace(time=lambda: float(frozen))
    )


@pytest.fixture
def session_factory(tmp_path):
    # Per-test isolated SQLite: this suite asserts HTTP behaviour (429 /
    # Retry-After / subject isolation), which is engine-agnostic — the
    # engine-sensitive atomic-increment logic is covered on Postgres by
    # tests/db/test_rate_limit_repository.py. An isolated file avoids the
    # shared-DB lock that TestClient's own connection would trigger on SQLite.
    url = f"sqlite:///{tmp_path / 'rl.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())
    return factory


# --- core callable -------------------------------------------------------


@pytest.mark.parametrize("bad", [{"limit": 0}, {"window_seconds": 0}])
def test_rate_limit_factory_rejects_non_positive_policy(bad):
    kwargs = {"name": "t", "limit": 5, "window_seconds": 60, **bad}
    with pytest.raises(ValueError):
        rate_limit(**kwargs)


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


def test_enforce_fails_fast_before_independent_session_can_self_lock(session_factory):
    s = session_factory()
    try:
        # Any flushed request write holds SQLite's database-wide writer lock.
        # The old implementation opened another writer, waited five seconds,
        # then leaked OperationalError("database is locked").
        pending = models.User(user_id="pending-request-user")
        s.add(pending)
        s.flush()

        started = time.monotonic()
        with pytest.raises(RuntimeError, match="before the request session starts"):
            enforce_rate_limit(
                s,
                name="feedback",
                subject="u1",
                limit=3,
                window_seconds=60,
                now_epoch=1000,
            )
        assert time.monotonic() - started < 1
        # The guard must not commit or roll back caller-owned work.
        assert s.in_transaction()
        assert s.get(models.User, pending.user_id) is pending
    finally:
        s.rollback()
        s.close()

    with session_factory() as check:
        assert check.get(models.User, "pending-request-user") is None


# --- dependency over a throwaway app -------------------------------------


def _client(session_factory, user):
    app = FastAPI()
    settings = get_settings()
    register_exception_handlers(app, settings)
    register_middleware(app, settings)

    @app.post("/rl")
    def route(
        _: None = Depends(rate_limit(name="t", limit=2, window_seconds=60)),
    ) -> dict:
        return {"ok": True}

    @app.post("/direct")
    def direct_route(
        request: Request,
        session: _TestSessionDep,
    ) -> dict:
        enforce_rate_limit(
            session,
            name="direct",
            subject="direct-user",
            limit=1,
            window_seconds=60,
            request=request,
        )
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
    first = client.post("/rl")
    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"
    reset = first.headers["x-ratelimit-reset"]

    second = client.post("/rl")
    assert second.status_code == 200
    assert second.headers["x-ratelimit-limit"] == "2"
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert second.headers["x-ratelimit-reset"] == reset

    resp = client.post("/rl")
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") is not None
    assert resp.headers["x-ratelimit-limit"] == "2"
    assert resp.headers["x-ratelimit-remaining"] == "0"
    assert resp.headers["x-ratelimit-reset"] == reset
    assert resp.json()["error"] == "RateLimitError"


def test_direct_enforcement_populates_production_middleware_headers(session_factory):
    client = _client(
        session_factory, AuthUser(id="u1", email=None, role=None, claims={})
    )
    allowed = client.post("/direct")
    assert allowed.status_code == 200
    assert allowed.headers["x-ratelimit-limit"] == "1"
    assert allowed.headers["x-ratelimit-remaining"] == "0"
    reset = allowed.headers["x-ratelimit-reset"]

    blocked = client.post("/direct")
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]
    assert blocked.headers["x-ratelimit-limit"] == "1"
    assert blocked.headers["x-ratelimit-remaining"] == "0"
    assert blocked.headers["x-ratelimit-reset"] == reset


def test_dependency_isolates_subjects(session_factory):
    u1 = _client(session_factory, AuthUser(id="u1", email=None, role=None, claims={}))
    u1.post("/rl")
    u1.post("/rl")
    assert u1.post("/rl").status_code == 429
    # A different authed subject on the same DB is unaffected.
    u2 = _client(session_factory, AuthUser(id="u2", email=None, role=None, claims={}))
    assert u2.post("/rl").status_code == 200


def test_dependency_skips_when_no_subject(session_factory):
    # Anonymous with no principal -> limit skipped (auth layer decides).
    client = _client(session_factory, None)
    for _ in range(5):
        assert client.post("/rl").status_code == 200


def test_skipped_dependency_keeps_nominal_headers(session_factory):
    response = _client(session_factory, None).post("/rl")
    nominal = str(get_settings().rate_limit_nominal)
    assert response.headers["x-ratelimit-limit"] == nominal
    assert response.headers["x-ratelimit-remaining"] == nominal


def test_default_resolver_ignores_spoofable_query_user_id(session_factory):
    # An anonymous caller passing ?user_id=<anything> must NOT be limited under
    # a victim's id (no cross-user DoS) and must not be trusted as a subject.
    client = _client(session_factory, None)
    for _ in range(5):
        assert client.post("/rl?user_id=victim").status_code == 200


def _failing_client(session_factory, user):
    """App whose route raises AFTER the limiter (to prove counts still persist)."""
    app = FastAPI()
    settings = get_settings()
    register_exception_handlers(app, settings)
    register_middleware(app, settings)

    @app.post("/rl")
    def route(
        _: None = Depends(rate_limit(name="t", limit=2, window_seconds=60)),
    ) -> dict:
        raise RuntimeError("boom after the limiter")

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
    return TestClient(app, raise_server_exceptions=False)


def test_increment_persists_when_request_errors(session_factory):
    # The limiter must count traffic even when the request rolls back — the
    # increment commits in its own transaction, not the request's unit of work.
    client = _failing_client(
        session_factory, AuthUser(id="u1", email=None, role=None, claims={})
    )
    assert client.post("/rl").status_code == 500  # counted (count=1)
    assert client.post("/rl").status_code == 500  # counted (count=2)
    # Third hit exceeds the limit -> 429 from the limiter, proving the two
    # erroring requests were durably counted despite their rollback.
    assert client.post("/rl").status_code == 429
