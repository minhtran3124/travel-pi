"""Live weather lookup via Open-Meteo — a real async outbound HTTP call, keyless, with its own geocoder."""

import datetime
import logging

import httpx

from app.core.config import get_settings
from app.core.text import fold_diacritics
from app.data.cities import CITIES
from app.exceptions import (
    CityNotFoundError,
    DomainValidationError,
    WeatherUnavailableError,
)
from app.schemas.weather import (
    CurrentWeather,
    DailyForecast,
    PackingResponse,
    PackingSuggestion,
    WeatherLocation,
    WeatherResponse,
)

logger = logging.getLogger(__name__)

# WMO weather interpretation codes. https://open-meteo.com/en/docs
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
    """GET ``url`` and return parsed JSON; transport/HTTP errors become :class:`WeatherUnavailableError`."""
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


# City coords are static — cache successful geocodes indefinitely so a retry after a transient timeout reuses them; only hits are cached, so a miss/typo stays retryable.
_GEOCODE_CACHE: dict[str, dict] = {}


def clear_geocode_cache() -> None:
    """Empty the geocoding cache."""
    _GEOCODE_CACHE.clear()


def _seed_location_for(city: str) -> dict | None:
    """Return a geocoder-shaped location dict for ``city`` when it exactly matches a seeded city (case/diacritic-insensitive); ``None`` for no match or missing seed coords.

    Open-Meteo's geocoder sometimes resolves a seeded name to the wrong place
    entirely (e.g. "Jeju" to a town in Ethiopia); a seeded city's own coords
    are ground truth, so they take priority over the network geocoder.
    """
    target = fold_diacritics(city.strip().casefold())
    for entry in CITIES:
        if fold_diacritics(entry["name"].casefold()) != target:
            continue
        if entry.get("latitude") is None or entry.get("longitude") is None:
            return None
        return {
            "name": entry["name"],
            "latitude": entry["latitude"],
            "longitude": entry["longitude"],
            "country": entry.get("country"),
        }
    return None


async def geocode_city(city: str) -> dict | None:
    """Resolve a city name to its first geocoding match, or ``None`` (successful matches are cached). An exact seed match is preferred over the network geocoder — see :func:`_seed_location_for`."""
    key = city.strip().casefold()
    cached = _GEOCODE_CACHE.get(key)
    if cached is not None:
        return cached

    seed_location = _seed_location_for(city)
    if seed_location is not None:
        _GEOCODE_CACHE[key] = seed_location
        return seed_location

    settings = get_settings()
    data = await _fetch_json(
        settings.weather_geocoding_url,
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )
    results = data.get("results") or []
    location = results[0] if results else None
    if location is not None:
        _GEOCODE_CACHE[key] = location
    return location


# Open-Meteo rejects dated forecast queries beyond this horizon; computed relative to now so it rolls forward every day.
_FORECAST_HORIZON_DAYS = 15


async def get_weather(
    city: str,
    days: int | None = None,
    date: datetime.date | None = None,
) -> WeatherResponse:
    """Return current conditions plus a forecast for ``city``; with ``date`` set, the single-day forecast (a date beyond the horizon raises :class:`DomainValidationError`)."""
    settings = get_settings()

    if date is not None:
        today = datetime.datetime.now(datetime.timezone.utc).date()
        horizon = today + datetime.timedelta(days=_FORECAST_HORIZON_DAYS)
        if date > horizon:
            # The get_climate pointer lives in the detail, not only the hint: agent tools surface errors as str(e), which is detail alone.
            raise DomainValidationError(
                f"'{date.isoformat()}' is beyond the {_FORECAST_HORIZON_DAYS}-day "
                "weather forecast horizon. Call get_climate for typical/average "
                "conditions (monthly normals) instead — there is no per-day "
                "forecast that far out.",
                hint=(
                    "Open-Meteo has no per-day forecast that far out. Call "
                    "get_climate for typical/average conditions (monthly "
                    "normals) instead."
                ),
            )

    location = await geocode_city(city)
    if location is None:
        raise CityNotFoundError(
            f"Could not find a location named '{city}'",
            hint=(
                "Check the spelling, or use GET /cities?q=<partial-name> "
                "to find a supported city name."
            ),
        )

    params = {
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
        "timezone": "auto",
    }
    if date is not None:
        params["start_date"] = date.isoformat()
        params["end_date"] = date.isoformat()
    else:
        forecast_days = days if days is not None else settings.weather_forecast_days
        params["forecast_days"] = max(1, min(forecast_days, 16))

    data = await _fetch_json(settings.weather_forecast_url, params)

    # Defensive walk: convert an unexpected 200 body shape to WeatherUnavailableError instead of a raw KeyError/IndexError → 500.
    try:
        current = data["current"]
        daily = data["daily"]
        daily_dates: list = daily["time"]

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
                    date=daily_dates[i],
                    temp_min_c=daily["temperature_2m_min"][i],
                    temp_max_c=daily["temperature_2m_max"][i],
                    precipitation_probability_max=daily[
                        "precipitation_probability_max"
                    ][i],
                    weather_code=daily["weather_code"][i],
                    description=describe_code(daily["weather_code"][i]),
                )
                for i in range(len(daily_dates))
            ],
        )
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning(
            "Open-Meteo returned an unexpected response shape for %s: %s",
            city,
            exc,
        )
        raise WeatherUnavailableError(
            "Open-Meteo returned an unexpected response shape"
        ) from exc


_CODE_SEVERITY: dict[int, float] = {
    0: 0.0,
    1: 0.0,
    2: 0.1,
    3: 0.2,
    45: 0.4,
    48: 0.4,
    51: 0.4,
    53: 0.4,
    55: 0.4,
    56: 0.4,
    57: 0.4,
    61: 0.5,
    63: 0.5,
    80: 0.5,
    81: 0.5,
    65: 0.7,
    82: 0.7,
    66: 0.8,
    67: 0.8,
    71: 0.7,
    73: 0.7,
    75: 0.7,
    77: 0.7,
    85: 0.7,
    86: 0.7,
    95: 1.0,
    96: 1.0,
    99: 1.0,
}

_PRECIP_CODES = {
    51,
    53,
    55,
    56,
    57,
    61,
    63,
    65,
    66,
    67,
    71,
    73,
    75,
    77,
    80,
    81,
    82,
    85,
    86,
    95,
    96,
    99,
}


def _code_severity(code: int) -> float:
    """Return WMO code severity in [0.0, 1.0] (0.5 for unknown codes)."""
    return _CODE_SEVERITY.get(code, 0.5)


def compute_weather_score(day: DailyForecast) -> float:
    """Return a suitability score in [0.0, 1.0] for a single forecast day."""
    mean_temp = (day.temp_min_c + day.temp_max_c) / 2
    if 18 <= mean_temp <= 26:
        comfort = 1.0
    elif mean_temp < 18:
        comfort = max(0.0, 1 - (18 - mean_temp) / 12)
    else:
        comfort = max(0.0, 1 - (mean_temp - 26) / 12)

    precip_penalty = (day.precipitation_probability_max or 0) / 100
    severity = _code_severity(day.weather_code)
    score = 0.5 * comfort + 0.3 * (1 - precip_penalty) + 0.2 * (1 - severity)
    return round(min(1.0, max(0.0, score)), 2)


def _is_rainy(day: DailyForecast) -> bool:
    """True if a day has likely precipitation."""
    return (
        day.precipitation_probability_max or 0
    ) >= 40 or day.weather_code in _PRECIP_CODES


async def get_packing(
    city: str,
    days: int | None = None,
    date: datetime.date | None = None,
) -> PackingResponse:
    """Return packing suggestions for ``city`` based on the weather forecast."""
    resp = await get_weather(city, days=days, date=date)
    daily = resp.daily

    if not daily:
        return PackingResponse(
            location=resp.location,
            days=0,
            overall_low_c=0.0,
            overall_high_c=0.0,
            rainy_days=0,
            suggestions=[],
            attribution=resp.attribution,
        )

    overall_low = min(d.temp_min_c for d in daily)
    overall_high = max(d.temp_max_c for d in daily)
    rainy_days = sum(1 for d in daily if _is_rainy(d))

    suggestions: list[PackingSuggestion] = []

    suggestions.append(
        PackingSuggestion(
            category="Essentials",
            items=["passport/ID", "phone charger", "reusable water bottle"],
            reason="Basics for any trip.",
        )
    )

    # Hot and cold are independent: hot by day, cold at night (deserts, altitude) may need both.
    if overall_high >= 27:
        suggestions.append(
            PackingSuggestion(
                category="Hot-weather clothing",
                items=["light breathable shirts", "shorts", "sunglasses", "sunscreen"],
                reason=f"Highs reach {overall_high:.0f}°C.",
            )
        )
    if overall_low <= 12:
        suggestions.append(
            PackingSuggestion(
                category="Warm layers",
                items=["insulating jacket", "sweater", "long trousers"],
                reason=f"Lows drop to {overall_low:.0f}°C.",
            )
        )
    if overall_high < 27 and overall_low > 12:
        suggestions.append(
            PackingSuggestion(
                category="Mild-weather clothing",
                items=["light jacket", "long-sleeve shirts"],
                reason="Comfortable temperatures expected.",
            )
        )

    if rainy_days > 0:
        suggestions.append(
            PackingSuggestion(
                category="Rain gear",
                items=["umbrella", "waterproof jacket"],
                reason=f"Rain likely on {rainy_days} of {len(daily)} days.",
            )
        )

    if overall_high >= 24 and any(d.weather_code in (0, 1) for d in daily):
        suggestions.append(
            PackingSuggestion(
                category="Sun protection",
                items=["hat", "SPF 30+ sunscreen"],
                reason="Clear, sunny spells expected.",
            )
        )

    return PackingResponse(
        location=resp.location,
        days=len(daily),
        overall_low_c=overall_low,
        overall_high_c=overall_high,
        rainy_days=rainy_days,
        suggestions=suggestions,
        attribution=resp.attribution,
    )
