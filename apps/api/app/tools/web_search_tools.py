"""Live web-search tools (Tavily search, SerpAPI places) for the concierge.

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
from langgraph.runtime import get_runtime
from pydantic import Field

from app.core.config import get_settings
from app.core.rate_limit import enforce_rate_limit
from app.exceptions import AppError, RateLimitError, UpstreamError
from app.research.context import ResearchContext
from app.schemas.base import AppBaseModel
from app.services import injection_screen_service, web_search_service
from app.services.injection_screen_service import ScreenItem, Verdict
from app.tools._base import session_scope, tool_error

_NO_RESULTS = "No web results for this query."
_SNIPPET_MAX = 500
# URLs are identifiers the model must cite verbatim: bound them loosely, never mid-snippet.
_URL_MAX = 2048

_INJECTED_DESC = "Injected from graph state — never supplied by the model."


class SearchWebArgs(AppBaseModel):
    query: str = Field(..., description="Search query built from trip facts.")
    topic: Literal["general", "news"] = Field(
        "general",
        description=(
            "'news' for breaking news and advisories from the last few days; "
            "'general' for everything else, including upcoming events and festivals."
        ),
    )
    time_range: Literal["day", "week", "month"] | None = Field(
        None,
        description=(
            "Only keeps pages published within this window — leave it unset "
            "when looking for upcoming events or dates in the future."
        ),
    )
    domains: list[str] | None = Field(
        None,
        description="Optional allowlist of domains to restrict results to.",
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


def _cap(value: object, limit: int = _SNIPPET_MAX) -> str:
    return str(value)[:limit]


def _esc(value: object, limit: int = _SNIPPET_MAX) -> str:
    return html.escape(_cap(value, limit), quote=True)


def _verdict_attrs(verdict: Verdict) -> str:
    if not verdict.screened:
        return ' screened="false"'
    flagged = _esc(str(verdict.flagged).lower())
    p = _esc(f"{verdict.p:.2f}")
    return f' screened="true" flagged="{flagged}" p="{p}"'


def _block(
    source: object,
    title: object,
    body: str,
    verdict: Verdict | None = None,
) -> str:
    attrs = "" if verdict is None else _verdict_attrs(verdict)
    return (
        f'<web_result source="{_esc(source or "", _URL_MAX)}" title="{_esc(title or "")}"'
        f"{attrs}>{body}</web_result>"
    )


def _lines(
    item: dict,
    fields: tuple[str, ...],
    fmt=_esc,
) -> str:
    return "\n".join(
        f"{key}: {fmt(item[key])}" for key in fields if item.get(key) is not None
    )


_PLACE_FIELDS = ("rating", "reviews", "address", "hours")


def _search_item(item: dict) -> ScreenItem:
    return ScreenItem(
        title=_cap(item.get("title") or ""),
        text=_cap(item.get("snippet") or ""),
    )


def _place_item(pl: dict) -> ScreenItem:
    return ScreenItem(
        title=_cap(pl.get("name") or ""),
        text=_lines(pl, _PLACE_FIELDS, _cap),
    )


def _render_search(result: dict, verdicts: list[Verdict]) -> str:
    if not result.get("found"):
        return _NO_RESULTS
    return "\n".join(
        _block(
            item.get("url"),
            item.get("title"),
            _esc(item.get("snippet") or ""),
            verdicts[i] if verdicts else None,
        )
        for i, item in enumerate(result["results"])
    )


def _render_places(result: dict, verdicts: list[Verdict]) -> str:
    if not result.get("found"):
        return _NO_RESULTS
    return "\n".join(
        _block(
            pl.get("url"),
            pl.get("name"),
            _lines(pl, _PLACE_FIELDS),
            verdicts[i] if verdicts else None,
        )
        for i, pl in enumerate(result["places"])
    )


async def _verdicts(
    result: dict,
    key: str,
    build_item,
) -> list[Verdict]:
    """Screen the results; verdicts render only in ``enforce``. Fail-open: any
    screen error yields no attributes."""
    mode = get_settings().injection_screen_mode
    if mode == "off":
        return []
    items = [build_item(x) for x in result.get(key) or []]
    try:
        verdicts = await injection_screen_service.screen(items)
    except Exception:
        return []
    return verdicts if mode == "enforce" else []


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


def _enforce_run(run_id: str) -> None:
    settings = get_settings()
    with session_scope() as session:
        enforce_rate_limit(
            session,
            name="web_search_run",
            subject=run_id,
            limit=settings.web_search_research_run_limit,
            window_seconds=_RUN_WINDOW_SECONDS,
        )


# A week: a run (≤ research_timeout_s) almost never straddles a boundary, and the
# limiter still prunes old run rows. run_id is unique per run.
_RUN_WINDOW_SECONDS = 7 * 24 * 3600


async def _apply_run_cap() -> None:
    """Cap web calls per research run; a no-op outside a ``ResearchContext`` run."""
    try:
        runtime = get_runtime(ResearchContext)
    except RuntimeError:
        return
    ctx = runtime.context if runtime is not None else None
    if not isinstance(ctx, ResearchContext):
        return
    try:
        await asyncio.to_thread(_enforce_run, ctx.run_id)
    except RateLimitError:
        raise ToolException(
            "The web budget for this research run is used up; "
            "continue with the seeded tools."
        ) from None


@tool(args_schema=SearchWebArgs, response_format="content_and_artifact")
async def search_web(
    query: str,
    topic: Literal["general", "news"] = "general",
    time_range: Literal["day", "week", "month"] | None = None,
    domains: list[str] | None = None,
    user_id: Annotated[str | None, InjectedState("user_id")] = None,
) -> tuple[str, dict]:
    """Search the live web for general facts, recent news, or current events.

    Use only after internal tools return nothing, or when the question is
    time-sensitive. This also covers current or upcoming events and festivals: use
    topic="general" and put the city and month/dates in the query. Never use it for
    flight or hotel prices. Build the query from trip facts, never from the
    traveller's name or contact details. Cite every fact as [title](url).
    """
    if not user_id:
        raise ToolException("Web search needs a signed-in traveller.")
    try:
        # Run cap first: a call it refuses must not spend the traveller's hourly quota.
        await _apply_run_cap()
        await asyncio.to_thread(_enforce, user_id)
        result = await web_search_service.search_web(query, topic, time_range, domains)
        verdicts = await _verdicts(result, "results", _search_item)
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise tool_error(e) from e
    return _render_search(result, verdicts), result


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
        # Run cap first: a call it refuses must not spend the traveller's hourly quota.
        await _apply_run_cap()
        await asyncio.to_thread(_enforce, user_id)
        result = await web_search_service.find_places_live(query, near, language)
        verdicts = await _verdicts(result, "places", _place_item)
    except UpstreamError:
        raise
    except AppError as e:
        raise tool_error(e) from e
    return _render_places(result, verdicts), result


WEB_SEARCH_TOOLS = [search_web, find_places_live]
