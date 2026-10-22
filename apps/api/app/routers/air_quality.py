"""Live US-AQI + pollutants + short forecast by city, via the keyless Open-Meteo Air-Quality API."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.routers.tags import Tags
from app.schemas.air_quality import AirQualityResponse
from app.schemas.error import error_responses
from app.services import air_quality_service

router = APIRouter(prefix="/air-quality", tags=[Tags.air_quality])


@router.get(
    "",
    response_model=AirQualityResponse,
    summary="Get current air quality and a short forecast for a city",
    responses=error_responses(404, 422, 502),
)
async def get_air_quality(
    city: Annotated[
        str,
        Query(
            description="City name to look up, e.g. 'Da Nang' or 'Bangkok'",
            examples=["Da Nang"],
            min_length=1,
        ),
    ],
) -> AirQualityResponse:
    """Resolve ``city`` to coordinates and return live air quality."""
    return await air_quality_service.get_air_quality(city)
