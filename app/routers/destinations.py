"""Destination endpoints: city overview aggregate."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.enums import OverviewSection
from app.schemas.destination import DestinationOverviewResponse
from app.schemas.error import error_responses
from app.services import destination_service

router = APIRouter(prefix="/destinations", tags=["destinations"])


@router.get(
    "/{city}/overview",
    response_model=DestinationOverviewResponse,
    summary="Get a destination overview for a city",
    responses=error_responses(404, 422, 502),
)
async def get_destination_overview(
    city: Annotated[
        str,
        Path(
            description="City name — fuzzy (typo/case tolerant)", examples=["Da Nang"]
        ),
    ],
    include: Annotated[
        set[OverviewSection] | None,
        Query(description="Sections to include; defaults to all."),
    ] = None,
    place_limit: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum number of places to return"),
    ] = 5,
    tip_limit: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum number of tips to return"),
    ] = 5,
) -> DestinationOverviewResponse:
    """Return an aggregate overview of a destination city.

    Combines weather, top places, travel tips, and hotel highlights into a
    single response. Use ``include`` to restrict which sections are returned;
    omit it to receive all four. Unknown cities raise 404; unknown section
    names are rejected with 422 before the service is called.
    """
    sections = (
        {s.value for s in include}
        if include
        else {"weather", "places", "tips", "hotels"}
    )
    return await destination_service.get_overview(
        city,
        include=sections,
        place_limit=place_limit,
        tip_limit=tip_limit,
    )
