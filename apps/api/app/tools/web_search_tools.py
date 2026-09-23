"""Live web-search tools (Tavily search, SerpAPI events/places) for the concierge.

Untrusted third-party content: every provider value is HTML-escaped into a
``<web_result>`` block, snippets are capped, and the model-facing schema hides the
injected ``user_id``/``language``. Each call refuses without a signed-in traveller,
enforces a per-user hourly limit, then delegates cache + provider work to the
service. Nothing here logs the query, results, ``user_id`` or keys.
"""

from __future__ import annotations

import asyncio
import html
from typing import Annotated, Literal

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.core.config import get_settings
from app.core.rate_limit import enforce_rate_limit
from app.exceptions import AppError, UpstreamError
from app.schemas.base import AppBaseModel
from app.services import web_search_service
from app.tools._base import session_scope, tool_error

_NO_RESULTS = "No web results for this query."
_SNIPPET_MAX = 500

DateFilter = Literal["today", "tomorrow", "week", "next_week", "month", "next_month"]

_INJECTED_DESC = "Injected from graph state — never supplied by the model."


class SearchWebArgs(AppBaseModel):
    query: str = Field(..., description="Search query built from trip facts.")
    topic: Literal["general", "news"] = Field(
        "general",
        description="'news' for recent/current events, 'general' otherwise.",
    )
    time_range: Literal["day", "week", "month"] | None = Field(
        None,
        description="Recency window for results; omit for no time filter.",
    )
    domains: list[str] | None = Field(
        None,
        description="Optional allowlist of domains to restrict results to.",
    )
    user_id: Annotated[str | None, InjectedState("user_id")] = Field(
        default=None, description=_INJECTED_DESC
    )


class FindEventsArgs(AppBaseModel):
    place: str = Field(..., description="City or place to find events in.")
    date_filter: DateFilter | None = Field(
        None, description="Optional date window for the events."
    )
    language: Annotated[str, InjectedState("language")] = Field(
        default="en", description=_INJECTED_DESC
    )
    user_id: Annotated[str | None, InjectedState("user_id")] = Field(
        default=None, description=_INJECTED_DESC
    )


class FindPlacesLiveArgs(AppBaseModel):
    query: str = Field(..., description="What to look for (e.g. 'vegan restaurant').")
    near: str = Field(..., description="City or place to search near.")
    language: Annotated[str, InjectedState("language")] = Field(
        default="en", description=_INJECTED_DESC
    )
    user_id: Annotated[str | None, InjectedState("user_id")] = Field(
        default=None, description=_INJECTED_DESC
    )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _block(source: object, title: object, body: str) -> str:
    return (
        f'<web_result source="{_esc(source or "")}" title="{_esc(title or "")}">'
        f"{body}</web_result>"
    )


def _lines(item: dict, fields: tuple[str, ...]) -> str:
    return "\n".join(
        f"{key}: {_esc(str(item[key])[:_SNIPPET_MAX])}"
        for key in fields
        if item.get(key) is not None
    )


def _render_search(result: dict) -> str:
    if not result.get("found"):
        return _NO_RESULTS
    return "\n".join(
        _block(
            item.get("url"),
            item.get("title"),
            _esc((item.get("snippet") or "")[:_SNIPPET_MAX]),
        )
        for item in result["results"]
    )


def _render_events(result: dict) -> str:
    if not result.get("found"):
        return _NO_RESULTS
    return "\n".join(
        _block(ev.get("url"), ev.get("title"), _lines(ev, ("date", "venue", "address")))
        for ev in result["events"]
    )


def _render_places(result: dict) -> str:
    if not result.get("found"):
        return _NO_RESULTS
    return "\n".join(
        _block(
            pl.get("url"),
            pl.get("name"),
            _lines(pl, ("rating", "reviews", "address", "hours")),
        )
        for pl in result["places"]
    )


def _enforce(user_id: str) -> None:
    settings = get_settings()
    with session_scope() as session:
        enforce_rate_limit(
            session,
            name="web_search",
            subject=user_id,
            limit=settings.web_search_user_hourly_limit,
            window_seconds=3600,
        )


@tool(args_schema=SearchWebArgs, response_format="content_and_artifact")
async def search_web(
    query: str,
    topic: Literal["general", "news"] = "general",
    time_range: Literal["day", "week", "month"] | None = None,
    domains: list[str] | None = None,
    user_id: Annotated[str | None, InjectedState("user_id")] = None,
) -> tuple[str, dict]:
    """Search the live web for general facts or recent news about a destination.

    Use only after internal tools return nothing, or when the question is
    time-sensitive. Never use it for flight or hotel prices. Build the query from
    trip facts, never from the traveller's name or contact details. Cite every fact
    as [title](url).
    """
    if not user_id:
        raise ToolException("Web search needs a signed-in traveller.")
    try:
        await asyncio.to_thread(_enforce, user_id)
        result = await web_search_service.search_web(query, topic, time_range, domains)
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise tool_error(e) from e
    return _render_search(result), result


@tool(args_schema=FindEventsArgs, response_format="content_and_artifact")
async def find_events(
    place: str,
    date_filter: DateFilter | None = None,
    language: Annotated[str, InjectedState("language")] = "en",
    user_id: Annotated[str | None, InjectedState("user_id")] = None,
) -> tuple[str, dict]:
    """Find live events happening in a place, optionally within a date window.

    Use only after internal tools return nothing, or when the question is
    time-sensitive. Never use it for flight or hotel prices. Build the query from
    trip facts, never from the traveller's name or contact details. Cite every fact
    as [title](url).
    """
    if not user_id:
        raise ToolException("Web search needs a signed-in traveller.")
    try:
        await asyncio.to_thread(_enforce, user_id)
        result = await web_search_service.find_events(place, date_filter, language)
    except UpstreamError:
        raise
    except AppError as e:
        raise tool_error(e) from e
    return _render_events(result), result


@tool(args_schema=FindPlacesLiveArgs, response_format="content_and_artifact")
async def find_places_live(
    query: str,
    near: str,
    language: Annotated[str, InjectedState("language")] = "en",
    user_id: Annotated[str | None, InjectedState("user_id")] = None,
) -> tuple[str, dict]:
    """Find live places (venues, restaurants, shops) near a location.

    Use only after internal tools return nothing, or when the question is
    time-sensitive. Never use it for flight or hotel prices. Build the query from
    trip facts, never from the traveller's name or contact details. Cite every fact
    as [title](url).
    """
    if not user_id:
        raise ToolException("Web search needs a signed-in traveller.")
    try:
        await asyncio.to_thread(_enforce, user_id)
        result = await web_search_service.find_places_live(query, near, language)
    except UpstreamError:
        raise
    except AppError as e:
        raise tool_error(e) from e
    return _render_places(result), result


WEB_SEARCH_TOOLS = [search_web, find_events, find_places_live]
