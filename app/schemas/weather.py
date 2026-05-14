"""Weather schemas — live data sourced from Open-Meteo."""

from pydantic import Field

from app.schemas.base import AppBaseModel


class WeatherLocation(AppBaseModel):
    """The resolved location a weather query was answered for."""

    name: str
    country: str | None = None
    latitude: float
    longitude: float
    timezone: str


class CurrentWeather(AppBaseModel):
    """Current conditions at the resolved location."""

    time: str
    temperature_c: float
    apparent_temperature_c: float
    relative_humidity: int
    wind_speed_kmh: float
    weather_code: int
    description: str


class DailyForecast(AppBaseModel):
    """One day of forecast."""

    date: str
    temp_min_c: float
    temp_max_c: float
    precipitation_probability_max: int | None = None
    weather_code: int
    description: str


class WeatherResponse(AppBaseModel):
    """Response body for ``GET /weather``."""

    location: WeatherLocation
    current: CurrentWeather
    daily: list[DailyForecast]
    attribution: str = Field(
        default="Weather data by Open-Meteo.com (CC BY 4.0)",
        description="Open-Meteo requires attribution when displaying its data.",
    )
