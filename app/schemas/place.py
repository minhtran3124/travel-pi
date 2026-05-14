"""Place / attraction schemas."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class Place(AppBaseModel):
    """A point of interest — attraction, restaurant, café, activity, etc."""

    id: str
    name: str
    city: str
    country: str
    category: str  # attraction | restaurant | cafe | activity | nightlife | shopping
    description: str
    address: str
    rating: float = Field(ge=0, le=5)
    review_count: int
    price_level: int = Field(
        ge=1, le=4
    )  # 1=free/cheap  2=moderate  3=expensive  4=luxury
    opening_hours: str | None = None
    image_url: str
    tags: list[str]
    is_recommended: bool = False
    latitude: float | None = None
    longitude: float | None = None


class PlaceListResponse(PagedResponse[Place]):
    """Response body for ``GET /places`` (paginated list of all places)."""


class PlaceSearchResponse(PagedResponse[Place]):
    """Response body for ``GET /places/search``."""

    city: str | None = None
    category: str | None = None
    min_rating: float | None = None
    price_level: int | None = None
    recommended_only: bool = False
    sort: str = "rating_desc"
