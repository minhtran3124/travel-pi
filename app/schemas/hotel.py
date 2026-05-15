"""Hotel schemas: domain model, search/availability responses, booking request."""

from pydantic import ConfigDict, Field

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class Hotel(AppBaseModel):
    """A bookable hotel."""

    id: str  # Pattern: h_{city-prefix}_{NN}, e.g. "h_dn_01"
    code: str  # OTA property code: IATA city prefix + 3-digit seq, e.g. "DAD001"
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


# --- GET /hotels/search — browse hotels in a city (no dates) ------------------


class HotelSearchInfo(AppBaseModel):
    """Echo of the hotel search query, returned alongside the results."""

    city: str
    min_stars: int | None = None
    max_price: float | None = None
    amenities: list[str] | None = None


class HotelListResponse(PagedResponse[Hotel]):
    """Response body for ``GET /hotels`` (paginated list of all hotels)."""


class HotelSearchResponse(PagedResponse[Hotel]):
    """Response body for ``GET /hotels/search``."""

    search: HotelSearchInfo


# --- GET /hotels/availability — check rooms for specific dates/party ----------


class HotelAvailability(Hotel):
    """A hotel plus its room availability for a specific date range / party."""

    available: bool  # Enough free rooms *and* they can hold the party
    available_rooms: int  # Free rooms for the dates (0 = fully booked)
    max_occupancy_per_room: int  # Guests one room can hold
    nights: int
    total_price: float  # price_per_night × nights × rooms


class HotelAvailabilityInfo(AppBaseModel):
    """Echo of the availability query, returned alongside the results."""

    city: str
    check_in: str
    check_out: str
    nights: int
    rooms: int
    adults: int
    children: int
    min_stars: int | None = None
    max_price: float | None = None
    amenities: list[str] | None = None


class HotelAvailabilityResponse(PagedResponse[HotelAvailability]):
    """Response body for ``GET /hotels/availability``."""

    search: HotelAvailabilityInfo


# --- POST /hotels/book -------------------------------------------------------


class HotelBookingRequest(AppBaseModel):
    """Request body for ``POST /hotels/book``.

    Mirrors what a hotel actually collects to hold rooms: the chosen hotel,
    the stay dates, party size, and the guest's name and contact details.
    The nightly rate is *not* sent by the client — ``total_price`` is
    computed server-side (``price_per_night × nights × rooms``).
    """

    hotel_id: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    rooms: int = Field(default=1, ge=1)  # Number of rooms to book
    adults: int = Field(default=2, ge=1)  # Adults across all rooms
    children: int = Field(default=0, ge=0)  # Children across all rooms
    guest_name: str  # Full name of the lead guest, as on their ID
    guest_email: str  # Contact email for the reservation
    guest_phone: str  # Contact phone for the hotel (late arrival, changes)
    notes: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "hotel_id": "5c1a8d2c-5e1c-4d6f-9a73-2c3b9b0a4ac5",
                "check_in": "2026-06-01",
                "check_out": "2026-06-03",
                "rooms": 1,
                "adults": 2,
                "children": 0,
                "guest_name": "Nguyen Van A",
                "guest_email": "nguyen.a@example.com",
                "guest_phone": "+84 901 234 567",
                "notes": "Late arrival ~22:00",
            }
        }
    )
