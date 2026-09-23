"""Live web search via Tavily (general/news search) and SerpAPI (events, places).

Pure provider + bounded TTL cache + result/error mapping — no rate limiting (that
lives in the tool layer). Provider SDK exceptions are mapped to
:class:`WebSearchUpstreamError` (transient) or :class:`WebSearchError` (logic).
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
import serpapi
from tavily import (
    AsyncTavilyClient,
    BadRequestError,
    InvalidAPIKeyError,
    UsageLimitExceededError,
)
from tavily.errors import ForbiddenError as TavilyForbiddenError
from tavily.errors import TimeoutError as TavilyTimeoutError

from app.core.config import get_settings
from app.exceptions import WebSearchError, WebSearchUpstreamError

logger = logging.getLogger(__name__)

# A SerpAPI HTTP-200 body carrying this marker in ``error`` is "no results", not a failure.
_NO_RESULTS_MARKER = "hasn't returned any results"

# cache key -> (expires_at, value); insertion order drives oldest-first eviction.
_cache: dict[tuple, tuple[float, dict]] = {}


def _now() -> float:
    return time.monotonic()


def clear_cache() -> None:
    _cache.clear()


def _cache_get(key: tuple) -> dict | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if _now() >= expires_at:
        del _cache[key]
        return None
    return value


def _cache_set(
    key: tuple,
    value: dict,
    ttl: int,
) -> None:
    _cache[key] = (_now() + ttl, value)
    max_entries = get_settings().web_search_cache_max_entries
    while len(_cache) > max_entries:
        del _cache[next(iter(_cache))]


async def search_web(
    query: str,
    topic: str = "general",
    time_range: str | None = None,
    domains: list[str] | None = None,
) -> dict:
    settings = get_settings()
    key = settings.tavily_api_key
    if not settings.tavily_search_available or not key:
        raise WebSearchError()

    cache_key = (
        "tavily",
        "search",
        query.strip().casefold(),
        topic,
        time_range,
        tuple(domains) if domains else None,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("[web_search] provider=tavily engine=search cache=hit")
        return cached

    started = _now()
    try:
        async with AsyncTavilyClient(api_key=key) as client:
            data = await client.search(
                query,
                search_depth="basic",
                topic=topic,
                time_range=time_range,
                max_results=5,
                include_domains=domains,
                include_answer=False,
                include_raw_content=False,
                include_published_date=True,
                timeout=settings.web_search_timeout_seconds,
            )
    except TavilyTimeoutError as exc:
        raise WebSearchUpstreamError() from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            raise WebSearchUpstreamError() from exc
        raise WebSearchError() from exc
    except httpx.RequestError as exc:
        raise WebSearchUpstreamError() from exc
    except (
        InvalidAPIKeyError,
        TavilyForbiddenError,
        UsageLimitExceededError,
        BadRequestError,
    ) as exc:
        raise WebSearchError() from exc

    result = _map_tavily(data)
    ttl = (
        settings.web_search_news_cache_ttl_seconds
        if topic == "news"
        else settings.web_search_cache_ttl_seconds
    )
    _cache_set(cache_key, result, ttl)
    logger.info(
        "[web_search] provider=tavily engine=search cache=miss latency_ms=%d count=%d",
        int((_now() - started) * 1000),
        len(result["results"]),
    )
    return result


async def find_events(
    place: str,
    date_filter: str | None = None,
    language: str = "en",
) -> dict:
    hl = "vi" if language == "vi" else "en"
    params = {"engine": "google_events", "q": f"Events in {place}", "hl": hl}
    if language == "vi":
        params["gl"] = "vn"
    if date_filter:
        params["htichips"] = f"date:{date_filter}"

    if not get_settings().serpapi_search_available:
        raise WebSearchError()
    cache_key = ("serpapi", "google_events", place.strip().casefold(), date_filter, hl)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("[web_search] provider=serpapi engine=google_events cache=hit")
        return cached

    started = _now()
    body = await _serpapi_search(params)
    result = _map_events(body)
    _cache_set(cache_key, result, get_settings().web_search_cache_ttl_seconds)
    logger.info(
        "[web_search] provider=serpapi engine=google_events cache=miss latency_ms=%d count=%d",
        int((_now() - started) * 1000),
        len(result["events"]),
    )
    return result


async def find_places_live(
    query: str,
    near: str,
    language: str = "en",
) -> dict:
    hl = "vi" if language == "vi" else "en"
    params = {
        "engine": "google_maps",
        "type": "search",
        "q": f"{query} near {near}",
        "hl": hl,
    }

    if not get_settings().serpapi_search_available:
        raise WebSearchError()
    cache_key = (
        "serpapi",
        "google_maps",
        query.strip().casefold(),
        near.strip().casefold(),
        hl,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("[web_search] provider=serpapi engine=google_maps cache=hit")
        return cached

    started = _now()
    body = await _serpapi_search(params)
    result = _map_places(body)
    _cache_set(cache_key, result, get_settings().web_search_cache_ttl_seconds)
    logger.info(
        "[web_search] provider=serpapi engine=google_maps cache=miss latency_ms=%d count=%d",
        int((_now() - started) * 1000),
        len(result["places"]),
    )
    return result


async def _serpapi_search(params: dict) -> dict | None:
    settings = get_settings()
    key = settings.serpapi_api_key
    if not settings.serpapi_search_available or not key:
        raise WebSearchError()

    # A fresh dict per call: the SDK mutates params to inject the (never-logged) api_key.
    call_params = dict(params)

    def _run():
        client = serpapi.Client(
            api_key=key,
            timeout=settings.web_search_timeout_seconds,
        )
        return client.search(call_params)

    try:
        raw = await asyncio.to_thread(_run)
    except serpapi.TimeoutError as exc:
        raise WebSearchUpstreamError() from exc
    except serpapi.HTTPConnectionError as exc:
        raise WebSearchUpstreamError() from exc
    except serpapi.HTTPError as exc:
        if exc.status_code >= 500:
            raise WebSearchUpstreamError() from exc
        if _NO_RESULTS_MARKER in (exc.error or ""):
            return None
        raise WebSearchError() from exc

    body = raw.as_dict() if hasattr(raw, "as_dict") else dict(raw)
    error = body.get("error")
    if error:
        if _NO_RESULTS_MARKER in error:
            return None
        raise WebSearchError()
    return body


def _map_tavily(data: dict) -> dict:
    results = [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "snippet": item.get("content") or "",
            "published_date": item.get("published_date"),
        }
        for item in data.get("results") or []
    ]
    return {"found": bool(results), "results": results}


def _map_events(body: dict | None) -> dict:
    events = []
    for item in (body or {}).get("events_results") or []:
        date = item.get("date")
        when = None
        if isinstance(date, dict):
            when = date.get("when") or date.get("start_date")
        venue = item.get("venue")
        address = item.get("address")
        events.append(
            {
                "title": item.get("title") or "",
                "date": when,
                "venue": venue.get("name") if isinstance(venue, dict) else None,
                "address": ", ".join(address) if isinstance(address, list) else address,
                "url": item.get("link"),
            }
        )
    return {"found": bool(events), "events": events}


def _map_places(body: dict | None) -> dict:
    places = []
    for item in (body or {}).get("local_results") or []:
        url = item.get("website")
        place_id = item.get("place_id")
        if not url and place_id:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        places.append(
            {
                "name": item.get("title") or "",
                "rating": item.get("rating"),
                "reviews": item.get("reviews"),
                "address": item.get("address"),
                "hours": item.get("hours") or item.get("operating_hours"),
                "url": url,
            }
        )
    return {"found": bool(places), "places": places}
