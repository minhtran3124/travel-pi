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
from app.enums import TripItemKind, TripItemStatus
from app.exceptions import AppError
from app.schemas.trip import TripCreate, TripItemCreate
from app.services.trip_service import TripService
from app.tools._base import dump, log_tool_call, session_scope, tool_error

logger = logging.getLogger(__name__)


@tool
def get_trip_summary(
    trip_id: Annotated[
        str,
        InjectedState("trip_id"),
        Field(description="The trip to summarise."),
    ],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
) -> dict:
    """Get a trip's full snapshot: days, items, places, budget rollup, and gaps.

    Use this first to load context before answering questions or editing a trip.

    :param trip_id: The trip to summarise. Injected from graph state on the
        LangGraph agent path (not model-supplied there); a direct/MCP caller
        must pass it explicitly.
    :return: The trip's full snapshot.
    """
    log_tool_call("get_trip_summary", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            return dump(TripService(s, user_id).get_trip_detail(trip_id))
        except AppError as e:
            raise tool_error(e) from e


@tool
def get_trip_budget(
    trip_id: Annotated[
        str,
        InjectedState("trip_id"),
        Field(description="The trip to get the budget for."),
    ],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
) -> dict:
    """Get the trip's budget: caps, spent-by-category, and remaining amounts.

    :param trip_id: The trip to get the budget for. Injected from graph state
        on the LangGraph agent path (not model-supplied there); a direct/MCP
        caller must pass it explicitly.
    :return: The trip's budget rollup.
    """
    log_tool_call("get_trip_budget", {"trip_id": trip_id})
    with session_scope() as s:
        try:
            return dump(TripService(s, user_id).get_trip_budget(trip_id))
        except AppError as e:
            raise tool_error(e) from e


@tool
def list_trip_places(
    trip_id: Annotated[
        str,
        InjectedState("trip_id"),
        Field(description="The trip to list places for."),
    ],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
) -> list:
    """List the places shortlisted onto a trip.

    :param trip_id: The trip to list places for. Injected from graph state on
        the LangGraph agent path (not model-supplied there); a direct/MCP
        caller must pass it explicitly.
    :return: The places shortlisted onto the trip.
    """
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
    trip_id: Annotated[
        str,
        InjectedState("trip_id"),
        Field(description="The trip to shortlist the place onto."),
    ],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
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
        direct/MCP caller must pass it explicitly.
    :param source: 'catalog' (default) or 'saved'.
    :return: The created trip-place record.
    """
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
    trip_id: Annotated[
        str,
        InjectedState("trip_id"),
        Field(description="The trip to add the item to."),
    ],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
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
        caller must pass it explicitly.
    :param kind: One of place|activity|meal|transport|note.
    :param status: One of pending|booked|constraint|optional.
    :param notes: Optional free-text notes for the item.
    :param start_time: Optional start time for the item.
    :return: The created itinerary item.
    """
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
