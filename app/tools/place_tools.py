"""Place / attraction tools (specs/travel-agent Task 3.2).

Wrap ``PlaceService`` as LLM tools. Each opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. An unrecognised city returns an empty list (not an error) —
this is the service's documented behaviour.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.services.place_service import PlaceService
from app.tools._base import dump, session_scope


@tool
def search_places(
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    price_level: int | None = None,
) -> list:
    """Search places by city, category, minimum rating, or price level (1–4).

    An unknown or misspelled city returns an empty list rather than an error.
    Leave all args as None to list all seeded places.
    """
    with session_scope() as s:
        try:
            return dump(
                PlaceService(s).search_places(
                    city=city,
                    category=category,
                    min_rating=min_rating,
                    price_level=price_level,
                )
            )
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def nearby_places(
    place_id: str,
    radius_km: float = 5.0,
    category: str | None = None,
) -> dict:
    """Find places within radius_km of a known place (by id or PLC-XXXX code).

    Returns a dict with keys 'origin' (the anchor place) and 'nearby' (list,
    nearest-first). Raises if the origin place is unknown or has no coordinates.
    """
    with session_scope() as s:
        try:
            origin, results = PlaceService(s).nearby_places(
                place_id,
                radius_km=radius_km,
                category=category,
            )
            return {"origin": dump(origin), "nearby": dump(results)}
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def resolve_place(place_id: str, source: str = "catalog") -> dict | None:
    """Resolve a place by id or PLC-XXXX short code. source: 'catalog' | 'saved'.

    Returns the place dict, or None if not found.
    """
    with session_scope() as s:
        try:
            result = PlaceService(s).resolve(place_id, source)
            return dump(result)
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def parse_nl_query(query: str) -> dict:
    """Parse a free-text place query into structured filters.

    Returns a dict with city, category, min_rating, price_level fields
    (any unrecognised field comes back as None). Feed the result into
    search_places to execute the search.
    """
    with session_scope() as s:
        try:
            return dump(PlaceService(s).parse_nl_query(query))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def list_place_categories() -> list:
    """List all distinct place categories with display metadata (color, icon)."""
    with session_scope() as s:
        try:
            return dump(PlaceService(s).categories())
        except AppError as e:
            raise ToolException(str(e)) from e


PLACE_TOOLS = [
    search_places,
    nearby_places,
    resolve_place,
    parse_nl_query,
    list_place_categories,
]
