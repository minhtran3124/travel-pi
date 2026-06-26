"""City schema."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class City(AppBaseModel):
    """A city record returned by GET /cities."""

    name: str = Field(description="City name (display case).", examples=["Da Nang"])
    country: str = Field(description="Country.", examples=["Vietnam"])
    airport_codes: list[str] = Field(
        description="IATA airport codes serving this city.", examples=[["DAD"]]
    )
    hotel_count: int = Field(
        description="Number of hotels in the seed data for this city.", examples=[5]
    )
    latitude: float | None = Field(
        default=None, description="Latitude, decimal degrees."
    )
    longitude: float | None = Field(
        default=None, description="Longitude, decimal degrees."
    )


class CityListResponse(PagedResponse[City]):
    """Response body for ``GET /cities``."""
