"""Destination overview schemas for GET /destinations/{city}/overview."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.hotel import Hotel
from app.schemas.place import Place
from app.schemas.tip import Tip
from app.schemas.weather import WeatherResponse


class PriceRange(AppBaseModel):
    """Minimum and maximum price (USD) across a set of hotels."""

    min: float = Field(
        description="Lowest nightly rate in the set, USD.", examples=[60.0]
    )
    max: float = Field(
        description="Highest nightly rate in the set, USD.", examples=[350.0]
    )


class StarRange(AppBaseModel):
    """Minimum and maximum star rating across a set of hotels."""

    min: int = Field(description="Lowest star rating in the set.", examples=[3])
    max: int = Field(description="Highest star rating in the set.", examples=[5])


class HotelSummary(AppBaseModel):
    """Aggregated hotel statistics for a destination."""

    count: int = Field(
        description="Total number of hotels available in the city.", examples=[12]
    )
    price_range_usd: PriceRange | None = Field(
        default=None,
        description="Price range across all hotels in the city, in USD. None when no hotels found.",
    )
    star_range: StarRange | None = Field(
        default=None,
        description="Star-rating range across all hotels in the city. None when no hotels found.",
    )
    sample: list[Hotel] = Field(
        default=[],
        description="Up to 3 representative hotels, sorted by rating descending.",
    )


class DestinationOverviewResponse(AppBaseModel):
    """Response body for GET /destinations/{city}/overview.

    Bundles weather, top places, essential travel tips, and a hotel summary
    into a single read-only aggregate for a given city.
    """

    city: str = Field(
        description="Resolved city name (display case).", examples=["Da Nang"]
    )
    country: str = Field(
        description="Country the city belongs to.", examples=["Vietnam"]
    )
    latitude: float = Field(
        description="City centroid latitude, decimal degrees (WGS-84).",
        examples=[16.0544],
    )
    longitude: float = Field(
        description="City centroid longitude, decimal degrees (WGS-84).",
        examples=[108.2022],
    )
    weather: WeatherResponse | None = Field(
        default=None,
        description="Current weather and short-range forecast. None when the weather service is unavailable.",
    )
    top_places: list[Place] = Field(
        default=[],
        description="Up to 5 recommended attractions/restaurants in the city, sorted by rating.",
    )
    essential_tips: list[Tip] = Field(
        default=[],
        description="Essential travel tips applicable to this city or country.",
    )
    hotel_summary: HotelSummary | None = Field(
        default=None,
        description="Aggregated hotel statistics for the city. None when no hotels are found.",
    )
    attribution: str = Field(
        description="Required data-source attribution string (includes Open-Meteo credit when weather is present).",
        examples=["Weather data by Open-Meteo.com (CC BY 4.0)"],
    )
