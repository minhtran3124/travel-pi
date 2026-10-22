"""SC-13: with ``research_enabled`` false every research path is a clean 404.

The router is only wired into the app when the flag is on (``app/main.py``), so a
disabled deployment exposes no new surface at all.
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient

from tests.api.research import build_app


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    get_settings.cache_clear()


_PATHS = [
    ("POST", "/agent/trips/t1/research"),
    ("GET", "/agent/trips/t1/research"),
    ("GET", "/agent/research/r1"),
    ("GET", "/agent/research/r1/stream"),
    ("GET", "/agent/research/r1/files/research/flights.md"),
    ("PUT", "/agent/research/r1/files/research/flights.md"),
    ("POST", "/agent/research/r1/revise"),
]


def test_every_research_path_404_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "false")
    get_settings.cache_clear()
    app, _url, _store = build_app(tmp_path)
    client = TestClient(app)

    for method, path in _PATHS:
        resp = client.request(method, path, json={"content": "x"})
        assert resp.status_code == 404, (method, path, resp.status_code)
