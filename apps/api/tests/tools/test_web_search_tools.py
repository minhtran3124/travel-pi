"""Web-search tools: schema hiding, rate limit, untrusted-content escaping, error mapping.

The service functions are monkeypatched, so no test touches the network. The
rate-limit test drives the real ``enforce_rate_limit`` against a fresh SQLite DB
whose ``rate_limit_counters`` table exists; every other invoke test rides the same
per-test engine (function-scoped ``tmp_path`` → empty counter per test), so a
couple of calls never exhaust the 30/hour budget.
"""

import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from app.exceptions import UpstreamError, WebSearchError, WebSearchUpstreamError
from app.tools import web_search_tools
from app.tools.web_search_tools import (
    WEB_SEARCH_TOOLS,
    find_places_live,
    search_web,
)
from langchain_core.tools import ToolException


@pytest.fixture(autouse=True)
def _patch_session_scope(monkeypatch, tmp_path):
    """Point the tools' ``session_scope`` at a fresh per-test SQLite DB with the
    rate-limit table created, so the real limiter can count without a network or a
    shared writer lock."""
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


def _run(tool, args, user_id="u1"):
    """Plain-dict invoke → returns the model-facing content string."""
    return asyncio.run(tool.ainvoke({**args, "user_id": user_id}))


def _run_msg(tool, args, user_id="u1"):
    """tool_call invoke → returns a ToolMessage carrying content + artifact."""
    return asyncio.run(
        tool.ainvoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": tool.name,
                "args": {**args, "user_id": user_id},
            }
        )
    )


# --- schema: injected args hidden, every model-facing field described ---


def test_search_web_schema_hides_user_id_and_describes_fields():
    fields = search_web.tool_call_schema.model_fields
    assert "user_id" not in fields
    assert {"query", "topic", "time_range", "domains"} <= set(fields)
    for f in fields.values():
        assert f.description
    assert search_web.args_schema.__module__.startswith("app.tools")


def test_find_places_live_schema_hides_injected_and_describes_fields():
    fields = find_places_live.tool_call_schema.model_fields
    assert "user_id" not in fields and "language" not in fields
    assert {"query", "near"} <= set(fields)
    for f in fields.values():
        assert f.description


def test_web_search_tools_export_list():
    assert list(WEB_SEARCH_TOOLS) == [search_web, find_places_live]


# Each tool paired with its service function name and its model-facing args.
_TOOL_CASES = [
    (search_web, "search_web", {"query": "x"}),
    (find_places_live, "find_places_live", {"query": "coffee", "near": "Hanoi"}),
]
_TOOL_IDS = [t.name for t, _, _ in _TOOL_CASES]


# --- user_id gate: missing id refuses before any provider call ---


@pytest.mark.parametrize("tool, service_attr, args", _TOOL_CASES, ids=_TOOL_IDS)
def test_missing_user_id_raises_and_service_not_called(
    tool, service_attr, args, monkeypatch
):
    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        return {"found": False, "results": [], "events": [], "places": []}

    monkeypatch.setattr(web_search_tools.web_search_service, service_attr, fake)
    with pytest.raises(ToolException):
        asyncio.run(tool.ainvoke(dict(args)))
    assert calls["n"] == 0


# --- rate limit: 31st call in the window refuses; provider called 30 times ---


def test_search_web_rate_limit_blocks_31st_call(monkeypatch):
    from app.core import rate_limit as rate_limit_module

    # Freeze the limiter clock mid fixed-window so 31 fast calls share one budget.
    frozen = (int(time.time()) // 3600) * 3600 + 1800
    monkeypatch.setattr(
        rate_limit_module, "time", SimpleNamespace(time=lambda: float(frozen))
    )

    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        return {"found": False, "results": []}

    monkeypatch.setattr(web_search_tools.web_search_service, "search_web", fake)

    for _ in range(30):
        _run(search_web, {"query": "x"}, user_id="rl-user")
    with pytest.raises(ToolException):
        _run(search_web, {"query": "x"}, user_id="rl-user")
    assert calls["n"] == 30


# --- content: web_result tag, HTML escaping, snippet cap, clean artifact ---


def test_search_web_content_escapes_title_and_caps_snippet(monkeypatch):
    async def fake(*a, **k):
        return {
            "found": True,
            "results": [
                {
                    "title": 'a"b</web_result>',
                    "url": "http://x",
                    "snippet": "y" * 600,
                    "published_date": None,
                }
            ],
        }

    monkeypatch.setattr(web_search_tools.web_search_service, "search_web", fake)
    content = _run(search_web, {"query": "x"})
    assert '<web_result source="http://x"' in content
    assert 'title="a&quot;b&lt;/web_result&gt;"' in content
    assert "y" * 500 in content
    assert "y" * 501 not in content


def test_search_web_artifact_has_no_kind_or_raw_content(monkeypatch):
    async def fake(*a, **k):
        return {
            "found": True,
            "results": [
                {
                    "title": "t",
                    "url": "http://x",
                    "snippet": "s",
                    "published_date": None,
                }
            ],
        }

    monkeypatch.setattr(web_search_tools.web_search_service, "search_web", fake)
    msg = _run_msg(search_web, {"query": "x"})
    assert "kind" not in msg.artifact
    assert "raw_content" not in msg.artifact
    for item in msg.artifact["results"]:
        assert "raw_content" not in item


def test_search_web_no_results_content_message(monkeypatch):
    async def fake(*a, **k):
        return {"found": False, "results": []}

    monkeypatch.setattr(web_search_tools.web_search_service, "search_web", fake)
    content = _run(search_web, {"query": "x"})
    assert content == "No web results for this query."


def test_find_places_live_content_uses_web_result_tag(monkeypatch):
    async def fake(*a, **k):
        return {
            "found": True,
            "places": [
                {
                    "name": "Cafe",
                    "rating": 4.5,
                    "reviews": 120,
                    "address": "2 Side St",
                    "hours": "Open",
                    "url": "http://p",
                }
            ],
        }

    monkeypatch.setattr(web_search_tools.web_search_service, "find_places_live", fake)
    content = _run(find_places_live, {"query": "coffee", "near": "Hanoi"})
    assert content.count("<web_result") == 1
    assert 'title="Cafe"' in content
    assert "rating: 4.5" in content


# --- error mapping: transient propagates, logic wraps with __cause__ ---


@pytest.mark.parametrize("tool, service_attr, args", _TOOL_CASES, ids=_TOOL_IDS)
def test_reraises_upstream_error(tool, service_attr, args, monkeypatch):
    async def boom(*a, **k):
        raise WebSearchUpstreamError()

    monkeypatch.setattr(web_search_tools.web_search_service, service_attr, boom)
    with pytest.raises(UpstreamError):
        _run(tool, args)


@pytest.mark.parametrize("tool, service_attr, args", _TOOL_CASES, ids=_TOOL_IDS)
def test_wraps_websearch_error_with_cause(tool, service_attr, args, monkeypatch):
    async def boom(*a, **k):
        raise WebSearchError()

    monkeypatch.setattr(web_search_tools.web_search_service, service_attr, boom)
    with pytest.raises(ToolException) as ei:
        _run(tool, args)
    assert isinstance(ei.value.__cause__, WebSearchError)


def test_find_places_live_content_caps_each_field(monkeypatch):
    async def fake(*a, **k):
        return {
            "found": True,
            "places": [
                {
                    "name": "Cafe",
                    "rating": 4.5,
                    "reviews": 10,
                    "address": "x" * 900,
                    "hours": "monday: 8am-9pm",
                    "url": "http://p",
                }
            ],
        }

    monkeypatch.setattr(web_search_tools.web_search_service, "find_places_live", fake)
    content = _run(find_places_live, {"query": "coffee", "near": "Hanoi"})
    assert "x" * 501 not in content
    assert "x" * 500 in content
    assert "hours: monday: 8am-9pm" in content


def test_search_web_content_caps_title_and_source(monkeypatch):
    async def fake(*a, **k):
        return {
            "found": True,
            "results": [
                {
                    "title": "t" * 900,
                    "url": "http://x/" + "u" * 900,
                    "snippet": "s",
                    "published_date": None,
                }
            ],
        }

    monkeypatch.setattr(web_search_tools.web_search_service, "search_web", fake)
    content = _run(search_web, {"query": "q"})
    assert "t" * 501 not in content
    assert "t" * 500 in content
    assert "u" * 900 in content
