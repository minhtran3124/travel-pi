"""Feedback abuse limit on ``POST /agent/feedback``: a 404-rejected request still increments the counter (the limiter commits on its own transaction before the request unit of work)."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient
from test_feedback import ANON, OWNER, body, make_app, post, seed_message

LIMIT = 2


@pytest.fixture(autouse=True)
def _small_limit(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "feedback_rate_limit_max", LIMIT)
    monkeypatch.setattr(settings, "feedback_rate_limit_window_seconds", 60)


def _assert_429(resp):
    assert resp.status_code == 429, resp.text
    assert resp.headers["retry-after"]
    assert resp.headers["x-ratelimit-limit"] == str(LIMIT)
    assert resp.headers["x-ratelimit-remaining"] == "0"
    assert resp.json()["error"] == "RateLimitError"


def test_authenticated_subject_hits_429_after_limit(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    with TestClient(app) as client:
        for i in range(LIMIT):
            r = post(client, body(mid))
            assert r.status_code == 201, r.text
            assert r.headers["x-ratelimit-remaining"] == str(LIMIT - 1 - i)
        _assert_429(post(client, body(mid)))


def test_anonymous_and_authenticated_subjects_count_separately(tmp_path):
    """Same raw id as JWT sub and as anonymous id → two independent counters."""
    authed_app, sf = make_app(tmp_path, auth_user_id=OWNER)
    anon_app, _ = make_app(tmp_path, auth_user_id=None)
    mid_owner = seed_message(sf, owner=OWNER)
    mid_anon = seed_message(sf, owner=ANON)
    with TestClient(authed_app) as authed, TestClient(anon_app) as anon:
        for _ in range(LIMIT):
            assert post(authed, body(mid_owner)).status_code == 201
        _assert_429(post(authed, body(mid_owner)))
        # A body-supplied id equal to the authenticated id is namespaced
        # ``anon:<id>`` and must not share the exhausted counter.
        r = post(anon, body(mid_anon, anonymous_user_id=OWNER))
        assert r.status_code == 404
        r = post(anon, body(mid_anon, anonymous_user_id=ANON))
        assert r.status_code == 201
        assert post(anon, body(mid_anon, anonymous_user_id=ANON)).status_code == 201
        _assert_429(post(anon, body(mid_anon, anonymous_user_id=ANON)))


def test_rejected_404_requests_still_count(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=OWNER)
    mid = seed_message(sf, owner=OWNER)
    with TestClient(app) as client:
        for _ in range(LIMIT):
            assert post(client, body(str(uuid.uuid4()))).status_code == 404
        # The budget is gone even though nothing was written.
        _assert_429(post(client, body(mid)))


def test_no_principal_skips_limit_and_returns_401(tmp_path):
    app, sf = make_app(tmp_path, auth_user_id=None)
    mid = seed_message(sf, owner=ANON)
    with TestClient(app) as client:
        for _ in range(LIMIT + 2):
            r = post(client, body(mid))
            assert r.status_code == 401
