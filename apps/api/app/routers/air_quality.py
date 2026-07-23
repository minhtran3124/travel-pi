"""Air-quality endpoint: live US-AQI + pollutants + a short forecast by city.

Backed by the keyless Open-Meteo Air-Quality API. Like ``/weather`` this makes
a real outbound call; everything else in this backend is mock/in-memory.

Errors are domain exceptions raised by the service layer
(``CityNotFoundError`` → 404, ``WeatherUnavailableError`` → 502); the global
handler in ``app.main`` turns them into HTTP responses.
"""

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
    """Resolve ``city`` to coordinates and return live air quality.

    Returns 404 if the city name cannot be geocoded, and 502 if the upstream
    Open-Meteo Air-Quality service is unreachable or returns a malformed body.

    :param city: City name to look up.
    :return: The current air quality and short forecast.
    """
    return await air_quality_service.get_air_quality(city)
