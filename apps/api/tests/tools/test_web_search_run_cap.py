"""Per-run web budget cap for research runs (specs/gh-229 Task 1.2).

Rides the real ``enforce_rate_limit`` against a fresh SQLite ``rate_limit_counters``
table (function-scoped ``tmp_path`` → empty counter per test). The runtime lookup
is monkeypatched so no LangGraph graph is needed; the service is faked so no
network is touched.
"""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from app.agents.context import AgentContext
from app.research.context import ResearchContext
from app.tools import web_search_tools
from app.tools.web_search_tools import find_places_live, search_web
from langchain_core.tools import ToolException


@pytest.fixture(autouse=True)
def _patch_session_scope(monkeypatch, tmp_path):
    """Point the tools' ``session_scope`` at a fresh per-test SQLite DB with the
    rate-limit table created, so the real limiter can count the run bucket."""
    from app.db import models  # noqa: F401 — register ORM tables on Base
    from app.db.base import Base
    from app.db.engine import get_session_factory

    url = f"sqlite:///{tmp_path / 'rl.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())

    @contextmanager
    def scope():
        s = factory()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    monkeypatch.setattr(web_search_tools, "session_scope", scope)


def _research_ctx(run_id="run-1"):
    return ResearchContext(
        user_id="u1",
        trip_id="t1",
        run_id=run_id,
        language="en",
        timezone="UTC",
    )


def _set_runtime(monkeypatch, context):
    """Fake ``get_runtime`` to return a runtime carrying ``context``."""
    monkeypatch.setattr(
        web_search_tools,
        "get_runtime",
        lambda _schema: SimpleNamespace(context=context),
    )


def _no_runtime(monkeypatch):
    """Fake ``get_runtime`` to raise as it does outside a graph run."""

    def _raise(_schema):
        raise RuntimeError("no runtime")

    monkeypatch.setattr(web_search_tools, "get_runtime", _raise)


def _fake_service(monkeypatch):
    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        return {"found": False, "results": []}

    monkeypatch.setattr(web_search_tools.web_search_service, "search_web", fake)
    return calls


def _run(user_id="u1"):
    return asyncio.run(search_web.ainvoke({"query": "x", "user_id": user_id}))


def test_seventh_call_in_a_run_hits_the_budget(monkeypatch):
    _set_runtime(monkeypatch, _research_ctx())
    calls = _fake_service(monkeypatch)

    for _ in range(6):
        _run()
    with pytest.raises(ToolException) as ei:
        _run()

    assert "web budget for this research run is used up" in str(ei.value)
    assert calls["n"] == 6


def test_a_new_run_id_resets_the_count(monkeypatch):
    calls = _fake_service(monkeypatch)

    _set_runtime(monkeypatch, _research_ctx("run-a"))
    for _ in range(6):
        _run()
    with pytest.raises(ToolException):
        _run()

    _set_runtime(monkeypatch, _research_ctx("run-b"))
    _run()

    assert calls["n"] == 7


def test_agent_context_is_never_capped(monkeypatch):
    _set_runtime(monkeypatch, AgentContext())
    calls = _fake_service(monkeypatch)

    for _ in range(8):
        _run()

    assert calls["n"] == 8


def test_no_runtime_is_never_capped(monkeypatch):
    _no_runtime(monkeypatch)
    calls = _fake_service(monkeypatch)

    for _ in range(8):
        _run()

    assert calls["n"] == 8


def test_find_places_live_shares_the_run_budget(monkeypatch):
    _set_runtime(monkeypatch, _research_ctx())
    calls = {"n": 0}

    async def fake_places(*a, **k):
        calls["n"] += 1
        return {"found": False, "places": []}

    monkeypatch.setattr(
        web_search_tools.web_search_service,
        "find_places_live",
        fake_places,
    )
    for _ in range(6):
        asyncio.run(
            find_places_live.ainvoke({"query": "pho", "near": "Hanoi", "user_id": "u1"})
        )
    with pytest.raises(ToolException, match="web budget"):
        asyncio.run(
            find_places_live.ainvoke({"query": "pho", "near": "Hanoi", "user_id": "u1"})
        )
    assert calls["n"] == 6
