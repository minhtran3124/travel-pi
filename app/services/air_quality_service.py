"""Live air-quality lookup via the Open-Meteo Air-Quality API.

Like ``weather_service`` (which this module reuses for geocoding and the raw
HTTP fetch), this makes a *real* outbound call — the Air-Quality API is the
same keyless, CC-BY-4.0 Open-Meteo provider, just a different host.

It returns the current US-AQI snapshot plus the six standard pollutants, and a
short per-day *max*-AQI forecast aggregated from the hourly series. There is no
cache — this is point-in-time data, mirroring ``weather_service``.

Only ``get_air_quality`` is async (it awaits geocoding + the fetch); the
category mapping and forecast aggregation are pure sync helpers. Tests
monkeypatch ``weather_service._fetch_json`` to avoid hitting the network.
"""

import logging

from app.core.config import get_settings
from app.exceptions import CityNotFoundError, WeatherUnavailableError
from app.schemas.air_quality import AirQualityDay, AirQualityResponse
from app.schemas.weather import WeatherLocation
from app.services import weather_service

logger = logging.getLogger(__name__)

# US-AQI category band ceilings (inclusive). The label applies when the AQI is
# ≤ the bound and > the previous one; anything above the last bound is the
# final, open-ended category. https://www.airnow.gov/aqi/aqi-basics/
_AQI_GOOD = 50
_AQI_MODERATE = 100
_AQI_USG = 150  # Unhealthy for Sensitive Groups
_AQI_UNHEALTHY = 200
_AQI_VERY_UNHEALTHY = 300


def _us_aqi_category(value: int | None) -> str:
    """Map a US-AQI value to its category label; ``None`` → ``"Unknown"``."""
    if value is None:
        return "Unknown"
    if value <= _AQI_GOOD:
        return "Good"
    if value <= _AQI_MODERATE:
        return "Moderate"
    if value <= _AQI_USG:
        return "Unhealthy for Sensitive Groups"
    if value <= _AQI_UNHEALTHY:
        return "Unhealthy"
    if value <= _AQI_VERY_UNHEALTHY:
        return "Very Unhealthy"
    return "Hazardous"


def _build_forecast(hourly: dict, max_days: int) -> list[AirQualityDay]:
    """Aggregate the hourly US-AQI series into per-day max-AQI summaries.

    Groups hourly readings by calendar date (``YYYY-MM-DD`` prefix of each
    timestamp), takes the peak non-null AQI per day, and emits one
    :class:`AirQualityDay` per date in chronological order, capped at
    ``max_days``. A day with no usable readings yields ``max_us_aqi=None``
    (``"Unknown"``) — ``max([])`` is guarded so an all-null day never raises.
    """
    htime: list = hourly.get("time") or []
    haqi: list = hourly.get("us_aqi") or []

    by_date: dict[str, list[int]] = {}
    for i, ts in enumerate(htime):
        day = ts[:10]
        bucket = by_date.setdefault(day, [])
        value = haqi[i] if i < len(haqi) else None
        if value is not None:
            bucket.append(value)

    days: list[AirQualityDay] = []
    for day in list(by_date)[:max_days]:
        values = by_date[day]
        max_aqi = max(values) if values else None
        days.append(
            AirQualityDay(
                date=day,
                max_us_aqi=max_aqi,
                category=_us_aqi_category(max_aqi),
            )
        )
    return days


async def get_air_quality(city: str) -> AirQualityResponse:
    """Return the current air quality + a short max-AQI forecast for ``city``.

    Raises :class:`CityNotFoundError` (404) when the name cannot be geocoded,
    and :class:`WeatherUnavailableError` (502) when Open-Meteo is unreachable
    or returns a body we cannot parse.
    """
    settings = get_settings()

    location = await weather_service.geocode_city(city)
    if location is None:
        raise CityNotFoundError(
            f"Could not find a location named '{city}'",
            hint=(
                "Check the spelling, or use GET /cities?q=<partial-name> "
                "to find a supported city name."
            ),
        )

    data = await weather_service._fetch_json(
        settings.weather_air_quality_url,
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "us_aqi,pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,"
                "sulphur_dioxide,ozone"
            ),
            "hourly": "us_aqi",
            "forecast_days": settings.air_quality_forecast_days,
            "timezone": "auto",
        },
    )

    # Walk the response defensively — ``_fetch_json`` already converts transport
    # and HTTP errors to ``WeatherUnavailableError`` (502), but a 200 with an
    # unexpected/null-laden body would otherwise escape as a raw exception →
    # 500. Mirror ``weather_service.get_weather``.
    try:
        current = data["current"]
        time = current["time"]  # required; its absence means a broken body
        us_aqi = current.get("us_aqi")
        hourly = data.get("hourly") or {}

        return AirQualityResponse(
            location=WeatherLocation(
                name=location["name"],
                country=location.get("country"),
                latitude=location["latitude"],
                longitude=location["longitude"],
                timezone=data.get("timezone", "UTC"),
            ),
            time=time,
            us_aqi=us_aqi,
            category=_us_aqi_category(us_aqi),
            pm2_5=current.get("pm2_5"),
            pm10=current.get("pm10"),
            ozone=current.get("ozone"),
            nitrogen_dioxide=current.get("nitrogen_dioxide"),
            sulphur_dioxide=current.get("sulphur_dioxide"),
            carbon_monoxide=current.get("carbon_monoxide"),
            forecast=_build_forecast(hourly, settings.air_quality_forecast_days),
            attribution="Air quality data by Open-Meteo.com (CC BY 4.0)",
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning(
            "Open-Meteo air-quality returned an unexpected response shape for %s: %s",
            city,
            exc,
        )
        raise WeatherUnavailableError(
            "Open-Meteo returned an unexpected air-quality response"
        ) from exc
