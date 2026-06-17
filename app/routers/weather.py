"""Weather endpoint: live current conditions + short forecast by city name.

Backed by Open-Meteo (free, no API key). This is the one router that makes a
real outbound call — everything else in this backend is mock/in-memory.

Errors are domain exceptions raised by the service layer
(``CityNotFoundError`` → 404, ``WeatherUnavailableError`` → 502); the global
handler in ``app.main`` turns them into HTTP responses.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.error import error_responses
from app.schemas.weather import PackingResponse, WeatherResponse
from app.services import weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get(
    "",
    response_model=WeatherResponse,
    summary="Get current weather and a short forecast for a city",
    responses=error_responses(404, 422, 502),
)
async def get_weather(
    city: Annotated[
        str,
        Query(
            description="City name to look up, e.g. 'Da Nang' or 'Bangkok'",
            examples=["Da Nang"],
            min_length=1,
        ),
    ],
    days: Annotated[
        int,
        Query(
            description="Number of forecast days (1–16)",
            ge=1,
            le=16,
            examples=[3],
        ),
    ] = 3,
) -> WeatherResponse:
    """Resolve ``city`` to coordinates and return live weather from Open-Meteo.

    Returns 404 if the city name cannot be geocoded, and 502 if the upstream
    Open-Meteo service is unreachable.
    """
    return await weather_service.get_weather(city, days=days)


@router.get(
    "/packing",
    response_model=PackingResponse,
    summary="Packing & gear suggestions derived from a city's forecast",
    responses=error_responses(404, 422, 502),
)
async def get_packing(
    city: Annotated[
        str,
        Query(
            description="City name to look up, e.g. 'Da Nang' or 'Bangkok'",
            examples=["Da Nang"],
            min_length=1,
        ),
    ],
    days: Annotated[
        int,
        Query(
            description="Number of forecast days (1–16)",
            ge=1,
            le=16,
            examples=[7],
        ),
    ] = 3,
) -> PackingResponse:
    """Resolve ``city`` and return clothing/gear suggestions from the forecast.

    Returns 404 if the city cannot be geocoded, 502 if Open-Meteo is unreachable.
    """
    return await weather_service.get_packing(city, days=days)
