"""web_search_service: provider mapping, error mapping and the bounded TTL cache (specs/agent-web-search Task 2.1).

All tests are offline: the Tavily and SerpAPI SDK clients are monkeypatched where
the service module looks them up, and ``get_settings`` is replaced with a plain
namespace. ``-k error`` selects the SDK-error-mapping rows; ``-k cache`` selects
the cache behaviour (hit, TTL expiry, news TTL, over-cap eviction).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.services.web_search_service as wss
import httpx
import pytest
import requests
import serpapi
from app.exceptions import WebSearchError, WebSearchUpstreamError


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "tavily_search_available": True,
        "serpapi_search_available": True,
        "tavily_api_key": "tvly-key",
        "serpapi_api_key": "serp-key",
        "web_search_timeout_seconds": 10.0,
        "web_search_cache_ttl_seconds": 3600,
        "web_search_news_cache_ttl_seconds": 900,
        "web_search_cache_max_entries": 512,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_settings(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(wss, "get_settings", lambda: _settings(**overrides))


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    wss.clear_cache()
    _patch_settings(monkeypatch)
    yield
    wss.clear_cache()


# --- Tavily fake -----------------------------------------------------------


class _FakeTavily:
    def __init__(self, *, result=None, raises=None, counter=None):
        self._result = result if result is not None else {"results": []}
        self._raises = raises
        self._counter = counter
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self._counter is not None:
            self._counter["calls"] += 1
        if self._raises is not None:
            raise self._raises
        return self._result


def _tavily_factory(*, result=None, raises=None, counter=None):
    def _make(*args, **kwargs):
        return _FakeTavily(result=result, raises=raises, counter=counter)

    return _make


def _patch_tavily(monkeypatch, **kwargs):
    monkeypatch.setattr(wss, "AsyncTavilyClient", _tavily_factory(**kwargs))


# --- SerpAPI fake ----------------------------------------------------------


class _FakeSerp:
    def __init__(self, *, result=None, raises=None, counter=None):
        self._result = result if result is not None else {}
        self._raises = raises
        self._counter = counter

    def search(self, params):
        if self._counter is not None:
            self._counter["calls"] += 1
        if self._raises is not None:
            raise self._raises
        return self._result


def _patch_serp(monkeypatch, **kwargs):
    monkeypatch.setattr(serpapi, "Client", lambda **_: _FakeSerp(**kwargs))


def _serp_http_error(status: int, body: dict | None = None):
    resp = requests.Response()
    resp.status_code = status
    if body is not None:
        import json

        resp._content = json.dumps(body).encode()
    original = requests.exceptions.HTTPError(response=resp)
    return serpapi.HTTPError(original)


# --- mapping shape ---------------------------------------------------------


def test_search_web_maps_results_shape(monkeypatch):
    _patch_tavily(
        monkeypatch,
        result={
            "results": [
                {
                    "title": "Da Nang travel advisory",
                    "url": "https://example.com/a",
                    "content": "Some snippet",
                    "published_date": "2026-09-20",
                }
            ]
        },
    )
    out = asyncio.run(wss.search_web("advisory da nang"))
    assert out == {
        "found": True,
        "results": [
            {
                "title": "Da Nang travel advisory",
                "url": "https://example.com/a",
                "snippet": "Some snippet",
                "published_date": "2026-09-20",
            }
        ],
    }
    assert "raw_content" not in out["results"][0]


def test_find_events_maps_shape(monkeypatch):
    _patch_serp(
        monkeypatch,
        result={
            "events_results": [
                {
                    "title": "Fireworks Festival",
                    "date": {"when": "Sat, Jun 8"},
                    "address": ["Han River", "Da Nang"],
                    "link": "https://ev.example/1",
                    "venue": {"name": "Riverfront"},
                }
            ]
        },
    )
    out = asyncio.run(wss.find_events("Da Nang", date_filter="week", language="vi"))
    assert out == {
        "found": True,
        "events": [
            {
                "title": "Fireworks Festival",
                "date": "Sat, Jun 8",
                "venue": "Riverfront",
                "address": "Han River, Da Nang",
                "url": "https://ev.example/1",
            }
        ],
    }


def test_find_places_live_builds_maps_url_without_website(monkeypatch):
    _patch_serp(
        monkeypatch,
        result={
            "local_results": [
                {
                    "title": "Pho House",
                    "rating": 4.5,
                    "reviews": 120,
                    "address": "12 Tran Phu",
                    "operating_hours": {"monday": "8am-9pm"},
                    "place_id": "PID123",
                }
            ]
        },
    )
    out = asyncio.run(wss.find_places_live("pho", near="My Khe Beach"))
    place = out["places"][0]
    assert out["found"] is True
    assert place["name"] == "Pho House"
    assert place["rating"] == 4.5
    assert place["reviews"] == 120
    assert place["hours"] == "monday: 8am-9pm"
    assert place["url"] == "https://www.google.com/maps/place/?q=place_id:PID123"


# --- Tavily error mapping --------------------------------------------------


def test_error_tavily_missing_key_maps_websearch(monkeypatch):
    _patch_settings(monkeypatch, tavily_search_available=False, tavily_api_key=None)
    with pytest.raises(WebSearchError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_timeout_maps_upstream(monkeypatch):
    _patch_tavily(monkeypatch, raises=wss.TavilyTimeoutError(10.0))
    with pytest.raises(WebSearchUpstreamError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_http_5xx_maps_upstream(monkeypatch):
    req = httpx.Request("POST", "https://api.tavily.com/search")
    err = httpx.HTTPStatusError(
        "server", request=req, response=httpx.Response(503, request=req)
    )
    _patch_tavily(monkeypatch, raises=err)
    with pytest.raises(WebSearchUpstreamError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_request_error_maps_upstream(monkeypatch):
    _patch_tavily(monkeypatch, raises=httpx.ConnectError("no route"))
    with pytest.raises(WebSearchUpstreamError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_invalid_api_key_maps_websearch(monkeypatch):
    _patch_tavily(monkeypatch, raises=wss.InvalidAPIKeyError("bad key"))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_forbidden_maps_websearch(monkeypatch):
    _patch_tavily(monkeypatch, raises=wss.TavilyForbiddenError("forbidden"))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_usage_limit_maps_websearch(monkeypatch):
    _patch_tavily(monkeypatch, raises=wss.UsageLimitExceededError("quota"))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.search_web("q"))


def test_error_tavily_bad_request_maps_websearch(monkeypatch):
    _patch_tavily(monkeypatch, raises=wss.BadRequestError("bad"))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.search_web("q"))


# --- SerpAPI error mapping -------------------------------------------------


def test_error_serpapi_missing_key_maps_websearch(monkeypatch):
    _patch_settings(monkeypatch, serpapi_search_available=False, serpapi_api_key=None)
    with pytest.raises(WebSearchError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_timeout_maps_upstream(monkeypatch):
    _patch_serp(monkeypatch, raises=serpapi.TimeoutError("timed out"))
    with pytest.raises(WebSearchUpstreamError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_connection_maps_upstream(monkeypatch):
    conn = requests.exceptions.ConnectionError("refused")
    _patch_serp(monkeypatch, raises=serpapi.HTTPConnectionError(conn))
    with pytest.raises(WebSearchUpstreamError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_http_5xx_maps_upstream(monkeypatch):
    _patch_serp(monkeypatch, raises=_serp_http_error(502))
    with pytest.raises(WebSearchUpstreamError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_http_401_maps_websearch(monkeypatch):
    _patch_serp(monkeypatch, raises=_serp_http_error(401))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_http_403_maps_websearch(monkeypatch):
    _patch_serp(monkeypatch, raises=_serp_http_error(403))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.find_places_live("cafe", near="Hoi An"))


def test_error_serpapi_http_429_maps_websearch(monkeypatch):
    _patch_serp(monkeypatch, raises=_serp_http_error(429))
    with pytest.raises(WebSearchError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_body_error_quota_maps_websearch(monkeypatch):
    _patch_serp(monkeypatch, result={"error": "Invalid API key provided."})
    with pytest.raises(WebSearchError):
        asyncio.run(wss.find_events("Hue"))


def test_error_serpapi_no_results_body_returns_found_false(monkeypatch):
    _patch_serp(
        monkeypatch,
        result={"error": "Google hasn't returned any results for this query."},
    )
    out = asyncio.run(wss.find_events("Nowhereville"))
    assert out == {"found": False, "events": []}


def test_error_serpapi_no_results_on_4xx_returns_found_false(monkeypatch):
    _patch_serp(
        monkeypatch,
        raises=_serp_http_error(
            400,
            {"error": "Google hasn't returned any results for this query."},
        ),
    )
    out = asyncio.run(wss.find_places_live("pho", "Nowhereville"))
    assert out == {"found": False, "places": []}


# --- cache -----------------------------------------------------------------


def test_cache_hit_serves_second_call_without_provider(monkeypatch):
    counter = {"calls": 0}
    _patch_tavily(
        monkeypatch,
        result={"results": [{"title": "t", "url": "u", "content": "c"}]},
        counter=counter,
    )
    first = asyncio.run(wss.search_web("same query"))
    second = asyncio.run(wss.search_web("same query"))
    assert first == second
    assert counter["calls"] == 1


def test_cache_ttl_expiry_refetches(monkeypatch):
    counter = {"calls": 0}
    _patch_tavily(monkeypatch, result={"results": []}, counter=counter)
    clock = {"t": 0.0}
    monkeypatch.setattr(wss, "_now", lambda: clock["t"])

    asyncio.run(wss.search_web("q"))
    clock["t"] = 3601.0  # past the 3600 s general TTL
    asyncio.run(wss.search_web("q"))
    assert counter["calls"] == 2


def test_cache_news_ttl_is_shorter(monkeypatch):
    counter = {"calls": 0}
    _patch_tavily(monkeypatch, result={"results": []}, counter=counter)
    clock = {"t": 0.0}
    monkeypatch.setattr(wss, "_now", lambda: clock["t"])

    asyncio.run(wss.search_web("headline", topic="news"))
    clock["t"] = 901.0  # past the 900 s news TTL but within the general TTL
    asyncio.run(wss.search_web("headline", topic="news"))
    assert counter["calls"] == 2


def test_cache_general_ttl_still_valid_at_news_horizon(monkeypatch):
    counter = {"calls": 0}
    _patch_tavily(monkeypatch, result={"results": []}, counter=counter)
    clock = {"t": 0.0}
    monkeypatch.setattr(wss, "_now", lambda: clock["t"])

    asyncio.run(wss.search_web("q", topic="general"))
    clock["t"] = 901.0  # past the news TTL, still inside the 3600 s general TTL
    asyncio.run(wss.search_web("q", topic="general"))
    assert counter["calls"] == 1


def test_cache_over_cap_evicts_oldest(monkeypatch):
    counter = {"calls": 0}
    _patch_settings(monkeypatch, web_search_cache_max_entries=2)
    _patch_tavily(monkeypatch, result={"results": []}, counter=counter)

    asyncio.run(wss.search_web("q1"))
    asyncio.run(wss.search_web("q2"))
    asyncio.run(wss.search_web("q3"))  # evicts q1
    asyncio.run(wss.search_web("q1"))  # miss again -> refetch
    assert counter["calls"] == 4
    # q3 is still cached, so no new call
    asyncio.run(wss.search_web("q3"))
    assert counter["calls"] == 4


def test_cache_serpapi_no_results_is_cached(monkeypatch):
    counter = {"calls": 0}
    _patch_serp(
        monkeypatch,
        result={"error": "Google hasn't returned any results for this query."},
        counter=counter,
    )
    asyncio.run(wss.find_events("Nowhereville"))
    asyncio.run(wss.find_events("Nowhereville"))
    assert counter["calls"] == 1


def test_cache_serpapi_hit_is_not_served_once_unavailable(monkeypatch):
    _patch_serp(monkeypatch, result={"events_results": [{"title": "Lantern night"}]})
    asyncio.run(wss.find_events("Hoi An"))
    _patch_settings(monkeypatch, serpapi_search_available=False)
    with pytest.raises(WebSearchError):
        asyncio.run(wss.find_events("Hoi An"))


def test_find_events_and_places_cap_results_at_five(monkeypatch):
    many = [{"title": f"t{i}"} for i in range(12)]
    _patch_serp(monkeypatch, result={"events_results": many, "local_results": many})
    events = asyncio.run(wss.find_events("Hanoi"))
    places = asyncio.run(wss.find_places_live("cafe", "Hanoi"))
    assert len(events["events"]) == 5
    assert len(places["places"]) == 5


def test_find_places_live_flattens_nested_hours(monkeypatch):
    _patch_serp(
        monkeypatch,
        result={
            "local_results": [
                {
                    "title": "Pho",
                    "operating_hours": {"monday": ["8am-12pm", "1pm-9pm"]},
                },
                {"title": "Bun", "hours": [{"tuesday": "9am-5pm"}]},
            ]
        },
    )
    out = asyncio.run(wss.find_places_live("pho", "Hanoi"))
    assert out["places"][0]["hours"] == "monday: 8am-12pm; 1pm-9pm"
    assert out["places"][1]["hours"] == "tuesday: 9am-5pm"


def test_search_web_sends_only_supported_tavily_arguments(monkeypatch):
    fake = _FakeTavily(result={"results": []})
    monkeypatch.setattr(wss, "AsyncTavilyClient", lambda *a, **k: fake)
    asyncio.run(wss.search_web("typhoon da nang", topic="news", time_range="week"))
    query, kwargs = fake.calls[0]
    assert query == "typhoon da nang"
    assert kwargs == {
        "search_depth": "basic",
        "topic": "news",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False,
        "time_range": "week",
        "include_domains": None,
        "timeout": 10.0,
    }


def test_find_events_joins_mixed_address_list(monkeypatch):
    _patch_serp(
        monkeypatch,
        result={"events_results": [{"title": "Fest", "address": ["Hoi An", 42]}]},
    )
    out = asyncio.run(wss.find_events("Hoi An"))
    assert out["events"][0]["address"] == "Hoi An, 42"
