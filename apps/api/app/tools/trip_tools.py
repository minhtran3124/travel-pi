"""Wrap ``TripService`` as LLM tools; injected args must be DECLARED in each ``args_schema`` or ToolNode never injects them."""

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
from app.schemas.base import AppBaseModel
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
    """A plain dict (not a raised exception) so ToolNode wraps it into a success ToolMessage that skips error handling."""
    return {
        "error": "no_active_trip",
        "message": "No trip was supplied for this call.",
        "hint": (
            "Identify the trip first: in a conversation, ask the traveller "
            "which trip is meant (not every assistant can create trips); "
            "otherwise pass a trip_id."
        ),
    }


class TripScopedArgs(AppBaseModel):
    """Injected owner + active trip shared by every trip-scoped tool."""

    user_id: Annotated[str | None, InjectedState("user_id")] = Field(
        default=None,
        description="The trip's owner. Injected from graph state (#118).",
    )
    trip_id: Annotated[str | None, InjectedState("trip_id")] = Field(
        default=None,
        description="The active trip. Injected from graph state — never supplied "
        "by the model.",
    )


class AddPlaceToTripArgs(TripScopedArgs):
    place_id: str = Field(..., description="The place's id or PLC-XXXX short code.")
    source: Literal["catalog", "saved"] = Field(
        "catalog",
        description="Where the place comes from: 'catalog' (default) or 'saved'.",
    )


class AddItineraryItemArgs(TripScopedArgs):
    day: int = Field(..., description="The trip day number the item belongs to.")
    title: str = Field(..., description="The item's title.")
    kind: TripItemKind = Field(
        TripItemKind.PLACE, description="The kind of itinerary entry."
    )
    status: TripItemStatus = Field(
        TripItemStatus.PENDING, description="Planning state of the item."
    )
    notes: str | None = Field(
        None, description="Optional free-text notes for the item."
    )
    start_time: str | None = Field(
        None, description="Optional start time for the item."
    )


class CreateTripArgs(AppBaseModel):
    title: str = Field(..., description="Trip title, e.g. 'Da Nang long weekend'.")
    city: str | None = Field(None, description="Primary destination city (free text).")
    start_date: str | None = Field(None, description="Trip start date (YYYY-MM-DD).")
    end_date: str | None = Field(None, description="Trip end date (YYYY-MM-DD).")
    travelers: int | None = Field(None, description="Number of travelers.")
    tool_call_id: Annotated[str, InjectedToolCallId]
    user_id: Annotated[str, InjectedState("user_id")] = Field(
        ...,
        description="The new trip's owner. Injected from graph state (#118).",
    )


class SetTripBudgetArgs(TripScopedArgs):
    flights: float | None = Field(None, ge=0, description="Flights cap in USD.")
    hotels: float | None = Field(None, ge=0, description="Hotels cap in USD.")
    activities: float | None = Field(None, ge=0, description="Activities cap in USD.")
    buffer: float | None = Field(
        None,
        ge=0,
        description="Buffer cap in USD (meals, local transport, incidentals).",
    )


class EstimateTripBudgetArgs(TripScopedArgs):
    nights: int | None = Field(
        None, description="Number of nights. Omit to derive from the trip's dates."
    )
    travelers: int | None = Field(
        None, description="Number of travelers. Omit to use the trip's value."
    )
    meal_style: MealStyle = Field(
        MealStyle.MID, description="Meal-spend tier: budget|mid|fine."
    )
    activity_level: ActivityLevel = Field(
        ActivityLevel.SOME, description="Activity-spend tier: none|some|lots."
    )
    flight_total_usd: float | None = Field(
        None, description="Known total flight cost in USD. Omit to exclude."
    )
    hotel_price_per_night_usd: float | None = Field(
        None, description="Known room price per night in USD. Omit to exclude."
    )


@tool(args_schema=TripScopedArgs)
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


@tool(args_schema=TripScopedArgs)
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


@tool(args_schema=TripScopedArgs)
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


@tool(args_schema=AddPlaceToTripArgs)
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


@tool(args_schema=AddItineraryItemArgs)
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


@tool(args_schema=TripScopedArgs)
def list_trips(
    user_id: Annotated[
        str | None,
        InjectedState("user_id"),
        Field(description="The trips' owner. Injected from graph state (#118)."),
    ] = None,
    trip_id: Annotated[
        str | None,
        InjectedState("trip_id"),
        Field(description="The trip that is currently open, if any."),
    ] = None,
) -> dict:
    """List every trip the traveller has, newest first, with a total count.

    This is the only way to know how many trips the traveller has, or what they
    are called. The trip context in the system prompt names the ONE trip
    currently open — it says nothing about how many exist — so never count or
    list trips from it. Call this tool to answer "how many trips do I have",
    "list my trips", or whenever the traveller names a trip that is not the
    open one.

    Each entry carries ``title``, ``city``, ``start_date``, ``end_date``,
    ``travelers``, ``items`` (the number of itinerary items) and ``is_active``
    (true for the trip currently open). Having no trip open is normal here and
    is not an error: every ``is_active`` is then false.

    :param trip_id: The trip that is currently open. Injected from graph state
        on the LangGraph agent path (not model-supplied there); optional, and
        used only to mark which entry is the open one.
    :return: ``{"count": <int>, "trips": [...]}`` — the trips, newest first.
    """
    if user_id is None:
        raise ToolException(
            "user_id was not supplied: it must be injected from graph state "
            "or passed explicitly by a direct/MCP caller."
        )
    log_tool_call("list_trips", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            trips = TripService(s, user_id).list_trips()
        except AppError as e:
            raise tool_error(e) from e
    entries = []
    for trip in trips:
        # dump() stringifies dates so the payload stays JSON-serialisable into the checkpoint.
        d = dump(trip)
        entries.append(
            {
                "title": d["title"],
                "city": d["city"],
                "start_date": d["start_date"],
                "end_date": d["end_date"],
                "travelers": d["travelers"],
                "items": len(d["items"]),
                "is_active": d["id"] == trip_id,
            }
        )
    return {"count": len(entries), "trips": entries}


TRIP_TOOLS = [
    get_trip_summary,
    get_trip_budget,
    list_trip_places,
    add_place_to_trip,
    add_itinerary_item,
    list_trips,
]


@tool(args_schema=CreateTripArgs)
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

    Call this only when the traveller wants to build or save an itinerary and
    there is no active trip yet — before shortlisting places or adding
    itinerary items. Never call it for a search on its own (flights, hotels,
    places): the search tools do not need a trip, so search first and open a
    trip only once the traveller wants to keep a result.

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
    # Refuse to stamp a trip with an anonymous caller's client-supplied id; only the agent path has a runtime to judge.
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


@tool(args_schema=SetTripBudgetArgs)
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
    if flights is None and hotels is None and activities is None and buffer is None:
        raise ToolException(
            "No cap supplied — nothing changed. set_trip_budget replaces ALL caps: "
            "pass every cap you want to keep, e.g. the confirmed suggested_caps."
        )
    log_tool_call("set_trip_budget", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            request = TripBudgetSet(
                flights=flights, hotels=hotels, activities=activities, buffer=buffer
            )
            return dump(TripService(s, user_id).set_trip_budget(trip_id, request))
        except AppError as e:
            raise tool_error(e) from e


@tool(args_schema=EstimateTripBudgetArgs)
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
    the line-item estimate plus ``suggested_caps``; categories whose estimated
    amount is zero — e.g. no price given for ``flights`` / ``hotels``, or
    ``activity_level`` none — are omitted and left uncapped. The caps present
    still sum to ``total_estimate``; confirm them with the traveller,
    then call ``set_trip_budget``. When the trip has no dates and ``nights`` is
    not given, a guidance value is returned instead — ask, never guess.

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
    # Only cap categories > 0: a stored 0.0 cap would reject the first booking.
    amounts = {
        "flights": round(b.flights, 2),
        "hotels": round(b.accommodation, 2),
        "activities": round(b.activities, 2),
        "buffer": round(
            b.meals + b.local_transport + (estimate.total_estimate - estimate.subtotal),
            2,
        ),
    }
    suggested_caps = {k: v for k, v in amounts.items() if v > 0}
    return dump(estimate) | {"suggested_caps": suggested_caps}
