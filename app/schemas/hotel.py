"""Hotel schemas: domain model, search response, and booking request."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class Hotel(AppBaseModel):
    """A bookable hotel."""

    id: str  # Pattern: h_{city-prefix}_{NN}, e.g. "h_dn_01"
    name: str
    city: str  # Display case, e.g. "Da Nang"
    country: str  # Derived from the city via cities.py, e.g. "Vietnam"
    address: str
    star_rating: int = Field(ge=1, le=5)
    price_per_night: float
    currency: str = "USD"
    amenities: list[str]
    image_url: str
    rating: float = Field(ge=0, le=5)
    review_count: int


class HotelSearchInfo(AppBaseModel):
    """Echo of the hotel search query, returned alongside the results."""

    city: str
    check_in: str
    check_out: str
    guests: int
    min_stars: int | None = None
    max_price: float | None = None
    amenities: list[str] | None = None


class HotelListResponse(PagedResponse[Hotel]):
    """Response body for ``GET /hotels`` (paginated list of all hotels)."""


class HotelSearchResponse(PagedResponse[Hotel]):
    """Response body for ``GET /hotels/search``."""

    search: HotelSearchInfo


class HotelBookingRequest(AppBaseModel):
    """Request body for ``POST /hotels/book``."""

    hotel_id: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guests: int = 1
    guest_name: str
    guest_email: str
    notes: str | None = None
