"""Air-quality schemas — live data sourced from Open-Meteo Air Quality API."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.weather import WeatherLocation


class AirQualityDay(AppBaseModel):
    """Air-quality summary for a single forecast day."""

    date: str = Field(description="Forecast date, YYYY-MM-DD.", examples=["2026-06-17"])
    max_us_aqi: int | None = Field(
        default=None,
        description="Peak US AQI value for the day. Null when data are unavailable.",
        examples=[42],
    )
    category: str = Field(
        description="US AQI category label for the day's peak value.",
        examples=["Good"],
    )


class AirQualityResponse(AppBaseModel):
    """Response body for ``GET /air-quality``."""

    location: WeatherLocation = Field(
        description="Resolved location the air-quality data applies to."
    )
    time: str = Field(
        description="Observation time for current readings, ISO 8601 local.",
        examples=["2026-06-16T14:00"],
    )
    us_aqi: int | None = Field(
        default=None,
        description="Current US AQI (0–500). Null when data are unavailable.",
        examples=[35],
    )
    category: str = Field(
        description="US AQI category for the current reading (e.g. 'Good', 'Moderate', 'Unhealthy').",
        examples=["Good"],
    )
    pm2_5: float | None = Field(
        default=None,
        description="Current PM2.5 concentration, μg/m³. Null when data are unavailable.",
        examples=[8.3],
    )
    pm10: float | None = Field(
        default=None,
        description="Current PM10 concentration, μg/m³. Null when data are unavailable.",
        examples=[15.1],
    )
    ozone: float | None = Field(
        default=None,
        description="Current surface ozone concentration, μg/m³. Null when data are unavailable.",
        examples=[62.4],
    )
    nitrogen_dioxide: float | None = Field(
        default=None,
        description="Current nitrogen dioxide (NO₂) concentration, μg/m³. Null when data are unavailable.",
        examples=[10.7],
    )
    sulphur_dioxide: float | None = Field(
        default=None,
        description="Current sulphur dioxide (SO₂) concentration, μg/m³. Null when data are unavailable.",
        examples=[2.1],
    )
    carbon_monoxide: float | None = Field(
        default=None,
        description="Current carbon monoxide (CO) concentration, μg/m³. Null when data are unavailable.",
        examples=[189.5],
    )
    forecast: list[AirQualityDay] = Field(
        default=[],
        description="Daily air-quality forecast, in date order (typically 7 days).",
    )
    attribution: str = Field(
        description="Required data-source attribution string.",
        examples=["Air quality data by Open-Meteo.com (CC BY 4.0)"],
    )
