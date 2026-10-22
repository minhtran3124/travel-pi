"""Conditional web-tool binding for the research subagents (gh-229 Task 1.1, SC-1/SC-2).

``available`` reads provider availability when it is called, i.e. on the next graph
build. With the flag off every filtered subagent list must equal the pre-change list
byte-for-byte; with the flag and keys on, ``entry_season`` gains ``search_web`` and
``days`` gains both web tools.
"""

import pytest
from app.core.config import get_settings

# Recorded from SUBAGENT_TOOLS before the web tools entered the lists.
_BEFORE: dict[str, list[str]] = {
    "flights": ["search_flights", "resolve_date"],
    "stays": ["search_hotels", "browse_hotels", "search_places", "nearby_places"],
    "days": [
        "search_places",
        "nearby_places",
        "resolve_place",
        "get_route",
        "get_city_route",
        "get_weather",
        "get_climate",
        "get_air_quality",
    ],
    "entry_season": [
        "get_visa",
        "get_local_tips",
        "search_travel_knowledge",
        "get_climate",
        "get_packing",
    ],
    "budget": ["get_trip_budget", "estimate_trip_budget"],
}


@pytest.fixture
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _configure(
    monkeypatch,
    *,
    enabled: bool,
    tavily: bool,
    serpapi: bool,
) -> None:
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key" if tavily else "")
    monkeypatch.setenv("SERPAPI_API_KEY", "serp-key" if serpapi else "")
    get_settings.cache_clear()


def _filtered_names() -> dict[str, list[str]]:
    from app.research.tools import SUBAGENT_TOOLS
    from app.tools.registry import available

    return {
        name: [t.name for t in available(SUBAGENT_TOOLS[name])]
        for name in SUBAGENT_TOOLS
    }


def _subagent_names() -> dict[str, list[str]]:
    from app.research.agent import _subagents

    return {sa["name"]: [t.name for t in sa["tools"]] for sa in _subagents()}


def test_flag_off_matches_pre_change(monkeypatch, clear_settings):
    # Keys present but the flag off: no web tool binds to any subagent.
    _configure(monkeypatch, enabled=False, tavily=True, serpapi=True)
    assert _filtered_names() == _BEFORE


def test_flag_on_both_keys_adds_web_tools(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=True, tavily=True, serpapi=True)
    filtered = _filtered_names()
    assert filtered["entry_season"] == _BEFORE["entry_season"] + ["search_web"]
    assert filtered["days"] == _BEFORE["days"] + ["search_web", "find_places_live"]
    for name in ("flights", "stays", "budget"):
        assert filtered[name] == _BEFORE[name]


def test_tavily_only_adds_search_web_to_days(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=True, tavily=True, serpapi=False)
    filtered = _filtered_names()
    assert filtered["days"] == _BEFORE["days"] + ["search_web"]
    assert filtered["entry_season"] == _BEFORE["entry_season"] + ["search_web"]


def test_subagents_bind_web_tools_when_available(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=True, tavily=True, serpapi=True)
    names = _subagent_names()
    assert "search_web" in names["entry_season"]
    assert "search_web" in names["days"]
    assert "find_places_live" in names["days"]


def test_subagents_exclude_web_tools_when_flag_off(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=False, tavily=True, serpapi=True)
    names = _subagent_names()
    for dimension in ("entry_season", "days"):
        assert "search_web" not in names[dimension]
        assert "find_places_live" not in names[dimension]
