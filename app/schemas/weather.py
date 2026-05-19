"""Weather schemas — live data sourced from Open-Meteo."""

from pydantic import Field

from app.schemas.base import AppBaseModel


class WeatherLocation(AppBaseModel):
    """The resolved location a weather query was answered for."""

    name: str = Field(description="Canonical place name as resolved by geocoding.")
    country: str | None = Field(default=None, description="Country, if known.")
    latitude: float = Field(description="Latitude, decimal degrees.")
    longitude: float = Field(description="Longitude, decimal degrees.")
    timezone: str = Field(
        description="IANA timezone name for the location.", examples=["Asia/Ho_Chi_Minh"]
    )


class CurrentWeather(AppBaseModel):
    """Current conditions at the resolved location."""

    time: str = Field(description="Observation time, ISO 8601 local.")
    temperature_c: float = Field(description="Air temperature, °C.")
    apparent_temperature_c: float = Field(description="Feels-like temperature, °C.")
    relative_humidity: int = Field(description="Relative humidity, percent.")
    wind_speed_kmh: float = Field(description="Wind speed at 10 m, km/h.")
    weather_code: int = Field(description="WMO weather-interpretation code.")
    description: str = Field(
        description="Human-readable summary of `weather_code`.", examples=["Light rain"]
    )


class DailyForecast(AppBaseModel):
    """One day of forecast."""

    date: str = Field(description="Forecast date, YYYY-MM-DD.")
    temp_min_c: float = Field(description="Daily minimum air temperature, °C.")
    temp_max_c: float = Field(description="Daily maximum air temperature, °C.")
    precipitation_probability_max: int | None = Field(
        default=None, description="Peak precipitation probability for the day, percent."
    )
    weather_code: int = Field(description="WMO weather-interpretation code.")
    description: str = Field(description="Human-readable summary of `weather_code`.")


class WeatherResponse(AppBaseModel):
    """Response body for ``GET /weather``."""

    location: WeatherLocation
    current: CurrentWeather
    daily: list[DailyForecast] = Field(
        description="Daily forecast, in date order (typically 7 days)."
    )
    attribution: str = Field(
        default="Weather data by Open-Meteo.com (CC BY 4.0)",
        description="Open-Meteo requires attribution when displaying its data.",
    )
