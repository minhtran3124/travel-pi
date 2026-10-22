"""Destination endpoints: city overview aggregate and climate normals."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.enums import OverviewSection
from app.routers.tags import Tags
from app.schemas.climate import ClimateResponse
from app.schemas.destination import DestinationOverviewResponse
from app.schemas.error import error_responses
from app.services import climate_service
from app.services.destination_service import DestinationService, get_destination_service

router = APIRouter(
    prefix="/destinations",
    tags=[Tags.destinations],
    responses=error_responses(404, 422),
)

DestinationDep = Annotated[DestinationService, Depends(get_destination_service)]


@router.get(
    "/{city}/overview",
    response_model=DestinationOverviewResponse,
    summary="Get a destination overview for a city",
)
async def get_destination_overview(
    destination: DestinationDep,
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
        Query(
            ge=1, le=20, description="Maximum number of places to return", examples=[5]
        ),
    ] = 5,
    tip_limit: Annotated[
        int,
        Query(
            ge=1, le=20, description="Maximum number of tips to return", examples=[5]
        ),
    ] = 5,
) -> DestinationOverviewResponse:
    """Return an aggregate overview (weather, places, tips, hotels) of a destination city.

    A weather-service outage does not fail the request: the ``weather`` section
    degrades to ``null`` and the rest is still returned.
    """
    sections = (
        {s.value for s in include} if include else {s.value for s in OverviewSection}
    )
    return await destination.get_overview(
        city,
        include=sections,
        place_limit=place_limit,
        tip_limit=tip_limit,
    )


@router.get(
    "/climate",
    response_model=ClimateResponse,
    summary="Get monthly climate normals for a destination city",
    responses=error_responses(502),
)
async def get_destination_climate(
    city: Annotated[
        str,
        Query(
            description="City name — fuzzy (typo/case tolerant)", examples=["Da Nang"]
        ),
    ],
    month: Annotated[
        int | None,
        Query(
            ge=1,
            le=12,
            description="Optional 1–12 to return just that month (omits best_months).",
        ),
    ] = None,
) -> ClimateResponse:
    """Return monthly climate normals for a destination city.

    ``month`` (1–12) returns just that month and omits ``best_months``. An
    unavailable or malformed Open-Meteo Archive response raises 502.
    """
    return await climate_service.get_climate(city, month=month)
