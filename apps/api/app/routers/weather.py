"""Live weather (current + short forecast) by city name, via Open-Meteo — the one router making a real outbound call."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.routers.tags import Tags
from app.schemas.error import error_responses
from app.schemas.weather import PackingResponse, WeatherResponse
from app.services import weather_service

router = APIRouter(
    prefix="/weather", tags=[Tags.weather], responses=error_responses(404, 422, 502)
)


@router.get(
    "",
    response_model=WeatherResponse,
    summary="Get current weather and a short forecast for a city",
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
    """Resolve ``city`` to coordinates and return live weather from Open-Meteo."""
    return await weather_service.get_weather(city, days=days)


@router.get(
    "/packing",
    response_model=PackingResponse,
    summary="Packing & gear suggestions derived from a city's forecast",
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
    """Resolve ``city`` and return clothing/gear suggestions from the forecast."""
    return await weather_service.get_packing(city, days=days)
