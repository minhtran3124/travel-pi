"""Trip & itinerary tools (specs/travel-agent Task 3.1).

Wrap ``TripService`` as LLM tools. Each opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. ``readOnly`` / ``destructive`` metadata is attached for the
manifest + MCP layer (roadmap B1) and lives in ``registry.py``.

``trip_id`` is injected by LangGraph from ``TravelAgentState.trip_id``
(``InjectedState``), mirroring ``user_id`` in ``memory_tools.py`` — the model
never sees or supplies the internal trip UUID (specs/agent-trip-context).

NOTE: these tools take ``trip_id`` as a LangGraph-injected arg
(``InjectedState``). An explicit ``args_schema=`` that omits an injected param
breaks ToolNode injection (it derives injection targets from the tool's
schema) — the tool then gets called without it and raises "missing required
positional arguments". So the model-facing descriptions are attached inline
via ``Annotated[..., Field(description=...)]`` on the signature, and no
explicit ``args_schema`` is passed: LangChain auto-derives the schema while
keeping the injected arg out of the model-facing ``tool_call_schema``.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, ToolException, tool
from langgraph.prebuilt import InjectedState
from langgraph.runtime import get_runtime
from langgraph.types import Command
from pydantic import Field

from app.agents.context import AgentContext
from app.enums import ActivityLevel, MealStyle, TripItemKind, TripItemStatus
from app.exceptions import AppError
from app.schemas.trip import (
    TripBudgetSet,
    TripCreate,
    TripEstimateRequest,
    TripItemCreate,
)
from app.services.trip_service import TripService, estimate_trip
from app.tools._base import dump, log_tool_call, session_scope, tool_error

logger = logging.getLogger(__name__)


def _no_active_trip() -> dict:
    """Guidance returned when a trip-scoped tool runs with no active trip.

    A plain dict return (not a raised ``ToolException`` / ``Command``) so
    ``ToolNode`` wraps it into a success ``ToolMessage`` that never passes
    through ``handle_tool_errors`` — the wording is identical across every
    sub-agent (specs/gh-125-trip-id-injection-keyerror/design.md).

    Worded for both callers: on the agent path ``trip_id`` is injected from
    graph state, but an MCP client may also omit it (it is optional in the
    served schema, ESCALATIONS E001), and that caller has no traveller to ask.
    """
    return {
        "error": "no_active_trip",
        "message": "No trip was supplied for this call.",
        "hint": (
            "Identify the trip first: in a conversation, ask the traveller "
            "which trip is meant (not every assistant can create trips); "
            "otherwise pass a trip_id."
        ),
    }


@tool
def get_trip_summary(
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to summarise."),
    ] = None,
) -> dict:
    """Get a trip's full snapshot: days, items, places, budget rollup, and gaps.

    Use this first to load context before answering questions or editing a trip.

    :param trip_id: The trip to summarise. Injected from graph state on the
        LangGraph agent path (not model-supplied there); a direct/MCP caller
        must pass it explicitly. When absent, the guidance value is returned.
    :return: The trip's full snapshot.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call("get_trip_summary", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            return dump(TripService(s, user_id).get_trip_detail(trip_id))
        except AppError as e:
            raise tool_error(e) from e


@tool
def get_trip_budget(
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to get the budget for."),
    ] = None,
) -> dict:
    """Get the trip's budget: caps, spent-by-category, and remaining amounts.

    :param trip_id: The trip to get the budget for. Injected from graph state
        on the LangGraph agent path (not model-supplied there); a direct/MCP
        caller must pass it explicitly. When absent, the guidance value is
        returned.
    :return: The trip's budget rollup.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call("get_trip_budget", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            return dump(TripService(s, user_id).get_trip_budget(trip_id))
        except AppError as e:
            raise tool_error(e) from e


@tool
def list_trip_places(
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to list places for."),
    ] = None,
) -> list | dict:
    """List the places shortlisted onto a trip.

    :param trip_id: The trip to list places for. Injected from graph state on
        the LangGraph agent path (not model-supplied there); a direct/MCP
        caller must pass it explicitly. When absent, the guidance value is
        returned.
    :return: The places shortlisted onto the trip.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call("list_trip_places", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            return dump(TripService(s, user_id).list_trip_places(trip_id))
        except AppError as e:
            raise tool_error(e) from e


@tool
def add_place_to_trip(
    place_id: Annotated[
        str, Field(description="The place's id or PLC-XXXX short code.")
    ],
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to shortlist the place onto."),
    ] = None,
    source: Annotated[
        Literal["catalog", "saved"],
        Field(
            description="Where the place comes from: 'catalog' (default) or 'saved'."
        ),
    ] = "catalog",
) -> dict:
    """Shortlist a place onto a trip.

    :param place_id: The place's id or PLC-XXXX short code.
    :param trip_id: The trip to shortlist the place onto. Injected from graph
        state on the LangGraph agent path (not model-supplied there); a
        direct/MCP caller must pass it explicitly. When absent, the guidance
        value is returned.
    :param source: 'catalog' (default) or 'saved'.
    :return: The created trip-place record.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call(
        "add_place_to_trip",
        {"trip_id": trip_id, "place_id": place_id, "source": source},
    )
    with session_scope() as s:
        try:
            return dump(
                TripService(s, user_id).add_place_to_trip(trip_id, place_id, source)
            )
        except AppError as e:
            raise tool_error(e) from e


@tool
def add_itinerary_item(
    day: Annotated[int, Field(description="The trip day number the item belongs to.")],
    title: Annotated[str, Field(description="The item's title.")],
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to add the item to."),
    ] = None,
    kind: Annotated[
        TripItemKind, Field(description="The kind of itinerary entry.")
    ] = TripItemKind.PLACE,
    status: Annotated[
        TripItemStatus, Field(description="Planning state of the item.")
    ] = TripItemStatus.PENDING,
    notes: Annotated[
        str | None, Field(description="Optional free-text notes for the item.")
    ] = None,
    start_time: Annotated[
        str | None, Field(description="Optional start time for the item.")
    ] = None,
) -> dict:
    """Add an itinerary item to a trip day.

    Use status='booked' to record something already reserved, and notes to
    capture details mid-trip.

    :param day: The trip day number the item belongs to.
    :param title: The item's title.
    :param trip_id: The trip to add the item to. Injected from graph state on
        the LangGraph agent path (not model-supplied there); a direct/MCP
        caller must pass it explicitly. When absent, the guidance value is
        returned.
    :param kind: One of place|activity|meal|transport|note.
    :param status: One of pending|booked|constraint|optional.
    :param notes: Optional free-text notes for the item.
    :param start_time: Optional start time for the item.
    :return: The created itinerary item.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call(
        "add_itinerary_item",
        {
            "trip_id": trip_id,
            "day": day,
            "title": title,
            "kind": kind,
            "status": status,
            "notes": notes,
            "start_time": start_time,
        },
    )
    with session_scope() as s:
        try:
            request = TripItemCreate(
                day=day,
                kind=kind,
                title=title,
                status=status,
                notes=notes,
                start_time=start_time,
            )
            return dump(TripService(s, user_id).add_item(trip_id, request))
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:  # pydantic validation on bad kind/status
            raise ToolException(str(e)) from e


TRIP_TOOLS = [
    get_trip_summary,
    get_trip_budget,
    list_trip_places,
    add_place_to_trip,
    add_itinerary_item,
]


@tool
def create_trip(
    title: Annotated[
        str, Field(description="Trip title, e.g. 'Da Nang long weekend'.")
    ],
    tool_call_id: Annotated[str, InjectedToolCallId],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The new trip's owner. Injected from graph state (#118)."),
    ],
    city: Annotated[
        str | None, Field(description="Primary destination city (free text).")
    ] = None,
    start_date: Annotated[
        str | None, Field(description="Trip start date (YYYY-MM-DD).")
    ] = None,
    end_date: Annotated[
        str | None, Field(description="Trip end date (YYYY-MM-DD).")
    ] = None,
    travelers: Annotated[int | None, Field(description="Number of travelers.")] = None,
) -> Command:
    """Create a new trip and make it the active trip for the rest of this turn.

    Call this when there is no active trip, before shortlisting places or
    adding itinerary items.

    :param title: Trip title, e.g. 'Da Nang long weekend'.
    :param tool_call_id: The originating tool call id, injected by LangGraph
        (not model-supplied) so the resulting ``ToolMessage`` can be matched
        back to this call.
    :param city: Primary destination city.
    :param start_date: Trip start date (YYYY-MM-DD).
    :param end_date: Trip end date (YYYY-MM-DD).
    :param travelers: Number of travelers.
    :return: A ``Command`` that sets the new trip as the active trip and
        emits a ``ToolMessage`` with the created trip.
    """
    log_tool_call(
        "create_trip",
        {
            "title": title,
            "city": city,
            "start_date": start_date,
            "end_date": end_date,
            "travelers": travelers,
        },
    )
    # #118: a trip needs a real owner. On the agent path an anonymous caller's
    # id is a client-supplied string, so a trip stamped with it belongs to
    # whoever sends that string next — refuse rather than create something
    # unownable. Only the agent path is judged here: off-graph (direct call or
    # MCP) there is no runtime and the caller passed `user_id` explicitly, so
    # there is nothing to infer. MCP has no caller identity at all, which is
    # recorded as out of scope on #118.
    try:
        runtime = get_runtime(AgentContext)
    except RuntimeError:
        runtime = None
    ctx = runtime.context if runtime is not None else None
    if ctx is not None and not ctx.authenticated:
        logger.info("[agent] tool=create_trip refused (anonymous caller)")
        return Command(
            update={
                "awaiting_user": True,
                "messages": [
                    ToolMessage(
                        content=(
                            "Not created: saving a trip needs a signed-in "
                            "traveller, and this conversation is anonymous. This "
                            "is not an outage and retrying will fail identically "
                            "— tell them their plan is safe in this chat, and "
                            "that signing in is what lets you save it."
                        ),
                        tool_call_id=tool_call_id,
                        status="error",
                    )
                ],
            }
        )

    with session_scope() as s:
        try:
            kwargs = {
                "title": title,
                "city": city,
                "start_date": start_date,
                "end_date": end_date,
            }
            if travelers is not None:
                kwargs["travelers"] = travelers
            request = TripCreate(**kwargs)
            trip = TripService(s, user_id).create_trip(request)
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:  # pydantic validation on bad dates
            raise ToolException(str(e)) from e

    return Command(
        update={
            "trip_id": trip.id,
            "messages": [
                ToolMessage(
                    content=json.dumps(dump(trip), ensure_ascii=False),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool
def set_trip_budget(
    flights: Annotated[
        float | None, Field(ge=0, description="Flights cap in USD.")
    ] = None,
    hotels: Annotated[
        float | None, Field(ge=0, description="Hotels cap in USD.")
    ] = None,
    activities: Annotated[
        float | None, Field(ge=0, description="Activities cap in USD.")
    ] = None,
    buffer: Annotated[
        float | None,
        Field(
            ge=0, description="Buffer cap in USD (meals, local transport, incidentals)."
        ),
    ] = None,
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to set the budget on."),
    ] = None,
) -> dict:
    """Set the trip's per-category budget caps (USD).

    Replace semantics: every call replaces ALL caps — omitted categories become
    uncapped. Call only after the traveller confirms the proposed caps (e.g. the
    ``suggested_caps`` from ``estimate_trip_budget``).

    :param flights: Flights cap in USD.
    :param hotels: Hotels cap in USD.
    :param activities: Activities cap in USD.
    :param buffer: Buffer cap in USD.
    :param trip_id: The trip to set the budget on. Injected from graph state on
        the LangGraph agent path (not model-supplied there); a direct/MCP
        caller must pass it explicitly. When absent, the guidance value is
        returned.
    :return: The resulting trip budget rollup.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call("set_trip_budget", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            request = TripBudgetSet(
                flights=flights, hotels=hotels, activities=activities, buffer=buffer
            )
            return dump(TripService(s, user_id).set_trip_budget(trip_id, request))
        except AppError as e:
            raise tool_error(e) from e


@tool
def estimate_trip_budget(
    nights: Annotated[
        int | None,
        Field(description="Number of nights. Omit to derive from the trip's dates."),
    ] = None,
    travelers: Annotated[
        int | None,
        Field(description="Number of travelers. Omit to use the trip's value."),
    ] = None,
    meal_style: Annotated[
        MealStyle, Field(description="Meal-spend tier: budget|mid|fine.")
    ] = MealStyle.MID,
    activity_level: Annotated[
        ActivityLevel, Field(description="Activity-spend tier: none|some|lots.")
    ] = ActivityLevel.SOME,
    flight_total_usd: Annotated[
        float | None,
        Field(description="Known total flight cost in USD. Omit to exclude."),
    ] = None,
    hotel_price_per_night_usd: Annotated[
        float | None,
        Field(description="Known room price per night in USD. Omit to exclude."),
    ] = None,
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip to estimate a budget for."),
    ] = None,
) -> dict:
    """Estimate a trip's budget and propose per-category caps (read-only).

    Derives ``nights`` and ``travelers`` from the trip when not supplied. Returns
    the line-item estimate plus ``suggested_caps`` (flights, hotels, activities,
    buffer) that sum to ``total_estimate``; confirm them with the traveller, then
    call ``set_trip_budget``. When the trip has no dates and ``nights`` is not
    given, a guidance value is returned instead — ask, never guess.

    :param nights: Number of nights; derived from the trip's dates when omitted.
    :param travelers: Number of travelers; the trip's value when omitted.
    :param meal_style: Meal-spend tier.
    :param activity_level: Activity-spend tier.
    :param flight_total_usd: Known total flight cost in USD.
    :param hotel_price_per_night_usd: Known room price per night in USD.
    :param trip_id: The trip to estimate for. Injected from graph state on the
        LangGraph agent path (not model-supplied there); a direct/MCP caller
        must pass it explicitly. When absent, the guidance value is returned.
    :return: The estimate with ``suggested_caps``, or a guidance value.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    if trip_id is None:
        return _no_active_trip()
    log_tool_call("estimate_trip_budget", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            trip = TripService(s, user_id).get_trip(trip_id)
        except AppError as e:
            raise tool_error(e) from e
    if nights is None and trip.start_date is not None and trip.end_date is not None:
        nights = max(1, (trip.end_date - trip.start_date).days)
    if nights is None:
        return {
            "error": "trip_dates_unknown",
            "hint": (
                "Ask the traveller how many nights the trip is (or its dates); "
                "do not guess."
            ),
        }
    if travelers is None:
        travelers = trip.travelers
    try:
        request = TripEstimateRequest(
            city=trip.city,
            nights=nights,
            travelers=travelers,
            flight_total_usd=flight_total_usd,
            hotel_price_per_night_usd=hotel_price_per_night_usd,
            meal_style=meal_style,
            activity_level=activity_level,
        )
    except ValueError as e:  # pydantic validation on nights=0 / negative price
        raise ToolException(str(e)) from e
    estimate = estimate_trip(request)
    b = estimate.breakdown
    return dump(estimate) | {
        "suggested_caps": {
            "flights": round(b.flights, 2),
            "hotels": round(b.accommodation, 2),
            "activities": round(b.activities, 2),
            "buffer": round(
                b.meals
                + b.local_transport
                + (estimate.total_estimate - estimate.subtotal),
                2,
            ),
        }
    }
