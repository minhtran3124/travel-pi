"""Destination endpoints: city overview aggregate and climate normals."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.enums import OverviewSection
from app.schemas.climate import ClimateResponse
from app.schemas.destination import DestinationOverviewResponse
from app.schemas.error import error_responses
from app.services import climate_service, destination_service

router = APIRouter(prefix="/destinations", tags=["destinations"])


@router.get(
    "/{city}/overview",
    response_model=DestinationOverviewResponse,
    summary="Get a destination overview for a city",
    responses=error_responses(404, 422),
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
    """Return an aggregate overview of a destination city.

    Combines weather, top places, travel tips, and hotel highlights into a
    single response. Use ``include`` to restrict which sections are returned;
    omit it to receive all four. Unknown cities raise 404; unknown section
    names are rejected with 422 before the service is called. A weather-service
    outage does not fail the request — the ``weather`` section degrades to
    ``null`` and the rest of the overview is still returned.
    """
    sections = (
        {s.value for s in include} if include else {s.value for s in OverviewSection}
    )
    return await destination_service.get_overview(
        city,
        include=sections,
        place_limit=place_limit,
        tip_limit=tip_limit,
    )


@router.get(
    "/climate",
    response_model=ClimateResponse,
    summary="Get monthly climate normals for a destination city",
    responses=error_responses(404, 422, 502),
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

    Provides average temperature (max/min), precipitation, rainy-day count, and
    a comfort label for each calendar month, derived from ~3 years of Open-Meteo
    historical archive data. Also includes ``best_months`` (the most comfortable
    months to visit) and a prose ``summary`` of the destination's climate.

    Pass ``month`` (1–12) to receive data for a single month only; ``best_months``
    is omitted from single-month responses. Omit ``month`` to receive all twelve
    months with full best-time guidance.

    Unknown cities raise 404. An invalid ``month`` value is rejected with 422
    before the service is called. If the Open-Meteo Archive API is unavailable
    or returns malformed data, the endpoint raises 502.
    """
    return await climate_service.get_climate(city, month=month)
