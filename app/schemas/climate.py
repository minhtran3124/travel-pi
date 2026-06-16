"""Climate schemas — monthly normals for GET /destinations/{city}/climate."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.weather import WeatherLocation


class ClimateMonth(AppBaseModel):
    """Climate normals for a single calendar month."""

    month: int = Field(
        description="Month number (1 = January, 12 = December).", examples=[7]
    )
    name: str = Field(description="Full calendar month name.", examples=["July"])
    avg_temp_max_c: float = Field(
        description="Average daily maximum temperature for the month, °C.",
        examples=[34.2],
    )
    avg_temp_min_c: float = Field(
        description="Average daily minimum temperature for the month, °C.",
        examples=[26.1],
    )
    avg_precip_mm: float = Field(
        description="Average total precipitation for the month, mm.", examples=[112.5]
    )
    rainy_days: int = Field(
        description="Average number of days with measurable rainfall in the month.",
        examples=[14],
    )
    comfort: str = Field(
        description="Short human-readable label summarising temperature and wetness conditions.",
        examples=["warm, wet"],
    )


class ClimateResponse(AppBaseModel):
    """Response body for ``GET /destinations/{city}/climate``.

    Returns monthly climate normals, best-time guidance, and a prose summary
    for the resolved location.
    """

    location: WeatherLocation = Field(
        description="Resolved location the climate data applies to."
    )
    based_on_years: list[int] = Field(
        description="Calendar years whose historical data were used to compute the normals.",
        examples=[[2000, 2001, 2002]],
    )
    months: list[ClimateMonth] = Field(
        description="Monthly climate normals in calendar order (January first)."
    )
    best_months: list[int] = Field(
        default=[],
        description="Month numbers (1–12) considered the best time to visit, based on comfort scores.",
        examples=[[1, 2, 12]],
    )
    summary: str = Field(
        description="Prose overview of the destination's climate and the best time to visit.",
        examples=[
            "Da Nang has a tropical monsoon climate. The driest and most comfortable months are January through April."
        ],
    )
    attribution: str = Field(
        description="Required data-source attribution string.",
        examples=["Weather data by Open-Meteo.com (CC BY 4.0)"],
    )
