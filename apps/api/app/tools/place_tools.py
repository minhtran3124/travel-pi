"""Place / attraction tools (specs/travel-agent Task 3.2).

Wrap ``PlaceService`` as LLM tools. Each opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. An unrecognised city returns an empty list (not an error) —
this is the service's documented behaviour.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.place_service import PlaceService
from app.tools._base import dump, log_tool_call, session_scope


class SearchPlacesArgs(AppBaseModel):
    city: str | None = Field(
        None,
        description="City to search within; fuzzy matched. None to search all cities.",
    )
    category: str | None = Field(None, description="Place category filter.")
    min_rating: float | None = Field(
        None, ge=0, le=5, description="Keep only places at or above this rating."
    )
    price_level: int | None = Field(
        None, ge=1, le=4, description="Price level filter (1-4)."
    )
    exclude_names: list[str] | None = Field(
        None,
        description=(
            "Place names to omit from the results — pass the names already suggested "
            "this conversation when the traveller asks for other/different options, "
            "instead of repeating the same search."
        ),
    )


class NearbyPlacesArgs(AppBaseModel):
    place_id: str = Field(
        ..., description="The anchor place's id or PLC-XXXX short code."
    )
    radius_km: float = Field(
        5.0, description="Search radius in kilometers (default 5.0)."
    )
    category: str | None = Field(
        None, description="Optional category filter for nearby results."
    )


class ResolvePlaceArgs(AppBaseModel):
    place_id: str = Field(..., description="The place's id or PLC-XXXX short code.")
    source: Literal["catalog", "saved"] = Field(
        "catalog", description="Where to resolve the place from: 'catalog' or 'saved'."
    )


class ParseNlQueryArgs(AppBaseModel):
    query: str = Field(..., description="Free-text place query.")


class ListPlaceCategoriesArgs(AppBaseModel):
    pass


@tool(args_schema=SearchPlacesArgs)
def search_places(
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    price_level: int | None = None,
    exclude_names: list[str] | None = None,
) -> list:
    """Search places by city, category, minimum rating, or price level (1–4).

    An unknown or misspelled city returns an empty list rather than an error.
    Leave all args as None to list all seeded places.

    :param city: City to search within; fuzzy matched. None to search all cities.
    :param category: Place category filter.
    :param min_rating: Keep only places at or above this rating.
    :param price_level: Price level filter (1-4).
    :param exclude_names: Place names to omit — pass prior suggestions on a follow-up.
    :return: Matching places.
    """
    log_tool_call("search_places", locals())
    with session_scope() as s:
        try:
            return dump(
                PlaceService(s).search_places(
                    city=city,
                    category=category,
                    min_rating=min_rating,
                    price_level=price_level,
                    exclude_names=exclude_names,
                )
            )
        except AppError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=NearbyPlacesArgs)
def nearby_places(
    place_id: str,
    radius_km: float = 5.0,
    category: str | None = None,
) -> dict:
    """Find places within radius_km of a known place (by id or PLC-XXXX code).

    Raises if the origin place is unknown or has no coordinates.

    :param place_id: The anchor place's id or PLC-XXXX short code.
    :param radius_km: Search radius in kilometers (default 5.0).
    :param category: Optional category filter for nearby results.
    :return: A dict with keys 'origin' (the anchor place) and 'nearby' (list,
        nearest-first).
    """
    log_tool_call("nearby_places", locals())
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


@tool(args_schema=ResolvePlaceArgs)
def resolve_place(place_id: str, source: str = "catalog") -> dict | None:
    """Resolve a place by id or PLC-XXXX short code.

    :param place_id: The place's id or PLC-XXXX short code.
    :param source: Where to resolve the place from: 'catalog' or 'saved'.
    :return: The place dict, or None if not found.
    """
    log_tool_call("resolve_place", locals())
    with session_scope() as s:
        try:
            result = PlaceService(s).resolve(place_id, source)
            return dump(result)
        except AppError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=ParseNlQueryArgs)
def parse_nl_query(query: str) -> dict:
    """Parse a free-text place query into structured filters.

    Feed the result into search_places to execute the search.

    :param query: Free-text place query.
    :return: A dict with city, category, min_rating, price_level fields (any
        unrecognised field comes back as None).
    """
    log_tool_call("parse_nl_query", locals())
    with session_scope() as s:
        try:
            return dump(PlaceService(s).parse_nl_query(query))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=ListPlaceCategoriesArgs)
def list_place_categories() -> list:
    """List all distinct place categories with display metadata (color, icon).

    :return: All place categories with display metadata.
    """
    log_tool_call("list_place_categories", locals())
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
