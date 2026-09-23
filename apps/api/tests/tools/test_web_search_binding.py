"""Conditional web-search binding for the concierge (specs/agent-web-search Task 4.1, SC-7).

``get_tools_for`` reads provider availability when it is called, i.e. on the next
graph build. With the flag off the concierge list must equal the pre-change list
byte-for-byte.
"""

import pytest
from app.core.config import get_settings

# Recorded from the concierge group before WEB_SEARCH_TOOLS entered the registry.
_CONCIERGE_BEFORE = [
    "search_places",
    "nearby_places",
    "resolve_place",
    "parse_nl_query",
    "list_place_categories",
    "get_weather",
    "get_packing",
    "get_air_quality",
    "get_climate",
    "get_route",
    "get_city_route",
    "get_local_tips",
    "get_visa",
    "browse_hotels",
    "search_hotels",
    "search_travel_knowledge",
    "resolve_date",
]


@pytest.fixture
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _concierge_names() -> list[str]:
    from app.tools.registry import get_tools_for

    return [t.name for t in get_tools_for("concierge")]


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


def test_flag_off_concierge_matches_pre_change(monkeypatch, clear_settings):
    # Keys present but the flag off: no web-search tool binds.
    _configure(monkeypatch, enabled=False, tavily=True, serpapi=True)
    assert _concierge_names() == _CONCIERGE_BEFORE


def test_flag_on_both_keys_binds_all_three(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=True, tavily=True, serpapi=True)
    assert _concierge_names() == _CONCIERGE_BEFORE + [
        "search_web",
        "find_events",
        "find_places_live",
    ]


def test_flag_on_tavily_only_binds_search_web(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=True, tavily=True, serpapi=False)
    assert _concierge_names() == _CONCIERGE_BEFORE + ["search_web"]


def test_flag_on_serpapi_only_binds_serpapi_tools(monkeypatch, clear_settings):
    _configure(monkeypatch, enabled=True, tavily=False, serpapi=True)
    assert _concierge_names() == _CONCIERGE_BEFORE + ["find_events", "find_places_live"]
