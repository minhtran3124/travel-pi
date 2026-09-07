"""Place / attraction tools (specs/travel-agent Task 3.2).

Wrap ``PlaceService`` as LLM tools. Each opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. An unrecognised city returns an empty list (not an error) —
this is the service's documented behaviour.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.content_translation_service import ContentTranslationService
from app.services.place_service import PlaceService
from app.streaming.panels import PlacesPanel
from app.tools._base import dump, log_tool_call, panel_result, session_scope, tool_error


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
    # Injected from graph state (TravelAgentState.language), never model-supplied:
    # the conversation language the supervisor detected. Free-form place text is
    # localized to it at tool time so the model and the Places panel see the same
    # words. Absent (MCP / direct calls) → default language, no translation.
    language: Annotated[str, InjectedState("language")] = Field(
        default="",
        description="Injected — never supplied by the model.",
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
    # Injected from graph state (TravelAgentState.user_id), never model-supplied.
    # Scopes the ``saved`` source to the signed-in traveller so a user-controlled
    # id/SPL- code can never read another user's saved place (PII). Kept on the
    # schema so ToolNode still injects it; stripped from the model-facing schema.
    user_id: Annotated[str, InjectedState("user_id")] = Field(
        default="",
        description="Injected — never supplied by the model.",
    )


class ParseNlQueryArgs(AppBaseModel):
    query: str = Field(..., description="Free-text place query.")


class ListPlaceCategoriesArgs(AppBaseModel):
    pass


# Cap the Places panel to the top N (highest-rated first, the service's default
# sort) so a broad/unfiltered query doesn't flood the drawer with the entire
# seeded set.
_PLACES_PANEL_CAP = 4


@tool(args_schema=SearchPlacesArgs, response_format="content_and_artifact")
def search_places(
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    price_level: int | None = None,
    exclude_names: list[str] | None = None,
    language: Annotated[str, InjectedState("language")] = "",
) -> tuple[str, dict | None]:
    """Search places by city, category, minimum rating, or price level (1–4).

    On matches the model sees a short summary and the top 4 (highest-rated first)
    are sent to the Places side panel. If nothing matches — either the city was not
    recognized or the filters left nothing — returns a short message and no panel;
    tell the user none were found and never invent places. It is not an error.
    Leave all args as None to list all seeded places.

    :param city: City to search within; fuzzy matched. None to search all cities.
    :param category: Place category filter.
    :param min_rating: Keep only places at or above this rating.
    :param price_level: Price level filter (1-4).
    :param exclude_names: Place names to omit — pass prior suggestions on a follow-up.
    :param language: Conversation language, injected from graph state (not
        model-supplied); place descriptions are localized to it.
    :return: A (summary, artifact) tuple. On matches the artifact is a
        ``{"kind": "places", "data": ...}`` side-panel payload capped at 4 places;
        on no match the artifact is ``None`` (no panel) and the summary explains
        the empty result.
    """
    log_tool_call("search_places", locals())
    with session_scope() as s:
        try:
            svc = PlaceService(s)
            results = svc.search_places(
                city=city,
                category=category,
                min_rating=min_rating,
                price_level=price_level,
                exclude_names=exclude_names,
            )
            if not results:
                if city and not svc.resolve_city(city):
                    return (
                        f"City '{city}' was not recognized, so no places could be "
                        "searched. Ask the user to confirm or correct the city — do "
                        "not invent places.",
                        None,
                    )
                return (
                    "No places matched those filters. Tell the user none were found "
                    "and suggest relaxing the filters — do not invent places.",
                    None,
                )
            total_count = len(results)
            top_results = ContentTranslationService(s).localize(
                "place", results[:_PLACES_PANEL_CAP], ["description"], language
            )
            canonical_city = top_results[0].city if city else None
            canonical_category = top_results[0].category if category else None
            where = f" in {canonical_city}" if canonical_city else ""
            what = f" {canonical_category}" if canonical_category else ""
            # Name the places the model must ground on: without these in the
            # content, the model only sees a count and invents well-known names
            # that diverge from the Places panel.
            listed = ", ".join(f"{p.name} ({p.rating:.1f}★)" for p in top_results)
            ground = (
                f" These exact places are shown in the Places panel: {listed}. "
                "Recommend only from these by name — do not invent other places."
            )
            if total_count > len(top_results):
                summary = (
                    f"Top {len(top_results)} of {total_count}{what} places{where} "
                    f"(highest-rated first).{ground} Offer to search again with "
                    "different filters or exclude_names if the traveller wants "
                    "more or different options."
                )
            else:
                summary = (
                    f"{total_count}{what} place{'s' if total_count != 1 else ''}"
                    f"{where}.{ground}"
                )
            return panel_result(
                summary,
                kind="places",
                data=PlacesPanel.from_places(
                    canonical_city, canonical_category, top_results
                ),
            )
        except AppError as e:
            raise tool_error(e) from e


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
            raise tool_error(e) from e


@tool(args_schema=ResolvePlaceArgs)
def resolve_place(
    place_id: str,
    source: str = "catalog",
    user_id: Annotated[str, InjectedState("user_id")] = "",
) -> dict | None:
    """Resolve a place by id or PLC-XXXX short code.

    :param place_id: The place's id or PLC-XXXX short code.
    :param source: Where to resolve the place from: 'catalog' or 'saved'.
    :param user_id: The signed-in traveller, injected from graph state (not
        model-supplied). Scopes the ``saved`` source to its owner; ``catalog``
        reads public data and ignores it.
    :return: The place dict, or None if not found.
    """
    log_tool_call("resolve_place", locals())
    with session_scope() as s:
        try:
            result = PlaceService(s).resolve(place_id, source, user_id=user_id)
            return dump(result)
        except AppError as e:
            raise tool_error(e) from e


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
            raise tool_error(e) from e


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
            raise tool_error(e) from e


PLACE_TOOLS = [
    search_places,
    nearby_places,
    resolve_place,
    parse_nl_query,
    list_place_categories,
]
