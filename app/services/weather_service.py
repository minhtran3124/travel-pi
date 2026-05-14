"""Live weather lookup via Open-Meteo.

Unlike the rest of this mock backend, this module makes a *real* outbound
HTTP call — Open-Meteo is free, needs no API key, and allows non-commercial
use of its hosted endpoint (data is CC BY 4.0). City names are resolved to
coordinates with Open-Meteo's own geocoding API, so the whole feature needs
exactly one provider and zero credentials.

The outbound call is fully async (``httpx.AsyncClient``) so the ``/weather``
route can be an ``async def`` without blocking the event loop — the FastAPI
best practice for routes that do real network I/O.

Tests monkeypatch ``_fetch_json`` to avoid hitting the network.
"""

import logging

import httpx

from app.core.config import get_settings
from app.exceptions import CityNotFoundError, WeatherUnavailableError
from app.schemas.weather import (
    CurrentWeather,
    DailyForecast,
    WeatherLocation,
    WeatherResponse,
)

logger = logging.getLogger(__name__)

# WMO weather interpretation codes — the numeric ``weather_code`` Open-Meteo
# returns for both current and daily data. https://open-meteo.com/en/docs
WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe_code(code: int) -> str:
    """Map a WMO weather code to a human-readable description."""
    return WMO_CODES.get(code, "Unknown")


# A representative emoji per WMO code — used by the HTML dashboard.
_WMO_EMOJI: dict[int, str] = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌧️",
    56: "🌧️",
    57: "🌧️",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    66: "🌧️",
    67: "🌧️",
    71: "🌨️",
    73: "🌨️",
    75: "❄️",
    77: "🌨️",
    80: "🌦️",
    81: "🌧️",
    82: "⛈️",
    85: "🌨️",
    86: "❄️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}


def emoji_for_code(code: int) -> str:
    """Map a WMO weather code to a representative emoji."""
    return _WMO_EMOJI.get(code, "🌡️")


async def _fetch_json(url: str, params: dict) -> dict:
    """GET ``url`` with ``params`` and return parsed JSON.

    Any transport/HTTP error is normalised to :class:`WeatherUnavailableError`
    so callers (and the router) never see raw ``httpx`` exceptions.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            timeout=settings.weather_timeout_seconds
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:  # covers timeouts, connection + status errors
        logger.warning("Open-Meteo request to %s failed: %s", url, exc)
        raise WeatherUnavailableError(str(exc)) from exc


async def geocode_city(city: str) -> dict | None:
    """Resolve a city name to its first geocoding match, or ``None``."""
    settings = get_settings()
    data = await _fetch_json(
        settings.weather_geocoding_url,
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    results = data.get("results") or []
    return results[0] if results else None


async def get_weather(city: str, days: int | None = None) -> WeatherResponse:
    """Return current conditions plus a ``days``-long forecast for ``city``.

    ``days`` defaults to the configured ``weather_forecast_days`` and is
    clamped to the 1-16 range Open-Meteo supports.

    Raises :class:`CityNotFoundError` if the name cannot be geocoded, and
    :class:`WeatherUnavailableError` if Open-Meteo is unreachable.
    """
    settings = get_settings()

    forecast_days = days if days is not None else settings.weather_forecast_days
    forecast_days = max(1, min(forecast_days, 16))

    location = await geocode_city(city)
    if location is None:
        raise CityNotFoundError(f"Could not find a location named '{city}'")

    data = await _fetch_json(
        settings.weather_forecast_url,
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "wind_speed_10m,weather_code"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,weather_code"
            ),
            "forecast_days": forecast_days,
            "timezone": "auto",
        },
    )

    current = data["current"]
    daily = data["daily"]

    return WeatherResponse(
        location=WeatherLocation(
            name=location["name"],
            country=location.get("country"),
            latitude=location["latitude"],
            longitude=location["longitude"],
            timezone=data.get("timezone", "UTC"),
        ),
        current=CurrentWeather(
            time=current["time"],
            temperature_c=current["temperature_2m"],
            apparent_temperature_c=current["apparent_temperature"],
            relative_humidity=current["relative_humidity_2m"],
            wind_speed_kmh=current["wind_speed_10m"],
            weather_code=current["weather_code"],
            description=describe_code(current["weather_code"]),
        ),
        daily=[
            DailyForecast(
                date=daily["time"][i],
                temp_min_c=daily["temperature_2m_min"][i],
                temp_max_c=daily["temperature_2m_max"][i],
                precipitation_probability_max=daily["precipitation_probability_max"][i],
                weather_code=daily["weather_code"][i],
                description=describe_code(daily["weather_code"][i]),
            )
            for i in range(len(daily["time"]))
        ],
    )
