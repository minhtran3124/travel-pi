"""City schema."""

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class City(AppBaseModel):
    """A city record returned by GET /cities."""

    name: str
    country: str
    airport_codes: list[str]
    hotel_count: int


class CityListResponse(PagedResponse[City]):
    """Response body for ``GET /cities``."""
