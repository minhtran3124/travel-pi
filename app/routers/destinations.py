"""Destination overview endpoint — agent-friendly one-call city snapshot."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.schemas.destination import DestinationOverview
from app.schemas.error import error_responses
from app.services import destination_service

router = APIRouter(prefix="/destinations", tags=["destinations"])


@router.get(
    "/{city}/overview",
    response_model=DestinationOverview,
    summary="One-call snapshot of a destination (places, tips, weather, hotels, airports)",
    responses=error_responses(404, 422),
)
async def destination_overview(
    city: Annotated[
        str,
        Path(
            description="Destination city name (fuzzy — typo/case tolerant)",
            examples=["Da Nang"],
        ),
    ],
    top_places: Annotated[
        int,
        Query(
            ge=1,
            le=20,
            description="How many top-rated places to include (1–20).",
            examples=[5],
        ),
    ] = 5,
) -> DestinationOverview:
    """Return everything an agent needs to size up a city in one request.

    Composes the top-rated places, essential local tips, live weather, hotel
    count, and serving airports for ``city``. Weather is best-effort — if the
    provider is unreachable the rest is still returned with ``weather: null``.
    Returns 404 if the city name can't be resolved.
    """
    return await destination_service.get_overview(city, top_places=top_places)
