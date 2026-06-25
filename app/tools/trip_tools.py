"""Trip & itinerary tools (specs/travel-agent Task 3.1).

Wrap ``TripService`` as LLM tools. Each opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. ``readOnly`` / ``destructive`` metadata is attached for the
manifest + MCP layer (roadmap B1) and lives in ``registry.py``.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.schemas.trip import TripItemCreate
from app.services.trip_service import TripService
from app.tools._base import dump, session_scope


@tool
def get_trip_summary(trip_id: str) -> dict:
    """Get a trip's full snapshot: days, items, places, budget rollup, and gaps.

    Use this first to load context before answering questions or editing a trip.
    """
    with session_scope() as s:
        try:
            return dump(TripService(s).get_trip_detail(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def get_trip_budget(trip_id: str) -> dict:
    """Get the trip's budget: caps, spent-by-category, and remaining amounts."""
    with session_scope() as s:
        try:
            return dump(TripService(s).get_trip_budget(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def list_trip_places(trip_id: str) -> list:
    """List the places shortlisted onto a trip."""
    with session_scope() as s:
        try:
            return dump(TripService(s).list_trip_places(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def add_place_to_trip(trip_id: str, place_id: str, source: str = "catalog") -> dict:
    """Shortlist a place onto a trip. source is 'catalog' (default) or 'saved'."""
    with session_scope() as s:
        try:
            return dump(TripService(s).add_place_to_trip(trip_id, place_id, source))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def add_itinerary_item(
    trip_id: str,
    day: int,
    title: str,
    kind: str = "place",
    status: str = "pending",
    notes: str | None = None,
    start_time: str | None = None,
) -> dict:
    """Add an itinerary item to a trip day.

    kind: place|food|transport|note|other. status: pending|booked|constraint|
    optional. Use status='booked' to record something already reserved, and
    notes to capture details mid-trip.
    """
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
            return dump(TripService(s).add_item(trip_id, request))
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:  # pydantic validation on bad kind/status
            raise ToolException(str(e)) from e


TRIP_TOOLS = [
    get_trip_summary,
    get_trip_budget,
    list_trip_places,
    add_place_to_trip,
    add_itinerary_item,
]
