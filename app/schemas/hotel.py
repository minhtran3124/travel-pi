"""Hotel schemas: domain model, search/availability responses, booking request."""

from pydantic import ConfigDict, Field, computed_field

from app.core.codes import prefixed_code
from app.schemas.base import AppBaseModel, RequestModel
from app.schemas.pagination import PagedResponse

# Prefix used for the friendly hotel short code, e.g. "HTL-AB23XY".
HOTEL_CODE_PREFIX = "HTL"


class Hotel(AppBaseModel):
    """A bookable hotel."""

    id: str = Field(
        description=(
            "Canonical hotel ID. Accepted by GET /hotels/{hotel_id} and as "
            "the `hotel_id` on POST /hotels/book. See `short_code` for a "
            "friendlier alternative."
        ),
        examples=["h_dn_01"],
    )
    code: str = Field(
        description=(
            "OTA-style property code: IATA city prefix + 3-digit sequence. "
            "Display only — not used for lookup."
        ),
        examples=["DAD001"],
    )
    name: str = Field(description="Hotel name.", examples=["Grand Da Nang Hotel"])
    city: str = Field(description="City (display case).", examples=["Da Nang"])
    country: str = Field(
        description="Country, derived from `city`.", examples=["Vietnam"]
    )
    address: str = Field(description="Street address.")
    star_rating: int = Field(
        ge=1, le=5, description="Star rating, 1–5.", examples=[4]
    )
    price_per_night: float = Field(
        description="Nightly rate for one room in `currency`.", examples=[120.0]
    )
    currency: str = Field(default="USD", description="ISO 4217 currency code.")
    amenities: list[str] = Field(
        description="Amenity tags, lowercased and free-form.",
        examples=[["wifi", "pool", "breakfast"]],
    )
    image_url: str = Field(description="URL of a hero image.")
    rating: float = Field(
        ge=0, le=5, description="Average guest rating 0–5.", examples=[4.6]
    )
    review_count: int = Field(
        description="Number of guest reviews.", examples=[842]
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_code(self) -> str:
        """Friendly ``HTL-XXXXXX`` reference derived from ``id``.

        Accepted anywhere a ``hotel_id`` is — easier to read aloud or quote
        in a chat message than the raw ID. The legacy ``code`` field is the
        OTA-style property code from the seed data, kept for compatibility.
        """
        return prefixed_code(HOTEL_CODE_PREFIX, self.id)


# --- GET /hotels/search — browse hotels in a city (no dates) ------------------


class HotelSearchInfo(AppBaseModel):
    """Echo of the hotel search query, returned alongside the results."""

    city: str = Field(description="City that was queried.", examples=["Da Nang"])
    min_stars: int | None = Field(
        default=None, description="Applied minimum-stars filter."
    )
    max_price: float | None = Field(
        default=None, description="Applied max-price-per-night filter."
    )
    amenities: list[str] | None = Field(
        default=None, description="Applied required-amenities filter."
    )


class HotelListResponse(PagedResponse[Hotel]):
    """Response body for ``GET /hotels`` (paginated list of all hotels)."""


class HotelSearchResponse(PagedResponse[Hotel]):
    """Response body for ``GET /hotels/search``."""

    search: HotelSearchInfo


# --- GET /hotels/availability — check rooms for specific dates/party ----------


class HotelAvailability(Hotel):
    """A hotel plus its room availability for a specific date range / party."""

    available: bool = Field(
        description=(
            "True when enough rooms are free AND the requested rooms can "
            "hold the party. Safe to book when true."
        ),
    )
    available_rooms: int = Field(
        description="Free rooms for the queried dates (0 = fully booked)."
    )
    max_occupancy_per_room: int = Field(
        description="Maximum guests per room (varies by star rating)."
    )
    nights: int = Field(description="Number of nights for the requested stay.")
    total_price: float = Field(
        description="All-in price: price_per_night × nights × rooms."
    )


class HotelAvailabilityInfo(AppBaseModel):
    """Echo of the availability query, returned alongside the results."""

    city: str = Field(description="City that was queried.")
    check_in: str = Field(description="Check-in date, YYYY-MM-DD.")
    check_out: str = Field(description="Check-out date, YYYY-MM-DD.")
    nights: int = Field(description="Stay length in nights.")
    rooms: int = Field(description="Rooms requested.")
    adults: int = Field(description="Adults in the party.")
    children: int = Field(description="Children in the party.")
    min_stars: int | None = Field(default=None, description="Min-stars filter applied.")
    max_price: float | None = Field(
        default=None, description="Max-price filter applied."
    )
    amenities: list[str] | None = Field(
        default=None, description="Required-amenities filter applied."
    )


class HotelAvailabilityResponse(PagedResponse[HotelAvailability]):
    """Response body for ``GET /hotels/availability``."""

    search: HotelAvailabilityInfo


# --- POST /hotels/book -------------------------------------------------------


class HotelBookingRequest(RequestModel):
    """Request body for ``POST /hotels/book``.

    Mirrors what a hotel actually collects to hold rooms: the chosen hotel,
    the stay dates, party size, and the guest's name and contact details.
    The nightly rate is *not* sent by the client — ``total_price`` is
    computed server-side (``price_per_night × nights × rooms``).
    """

    hotel_id: str = Field(
        description=(
            "Hotel canonical ID or short code (HTL-XXXXXX), case-insensitive. "
            "Get one from GET /hotels/search or /hotels/availability."
        ),
        examples=["h_dn_01", "HTL-AB23XY"],
    )
    check_in: str = Field(description="Check-in date, YYYY-MM-DD.", examples=["2026-06-01"])
    check_out: str = Field(
        description="Check-out date, YYYY-MM-DD. Must be after check_in.",
        examples=["2026-06-03"],
    )
    rooms: int = Field(default=1, ge=1, description="Number of rooms to book.")
    adults: int = Field(default=2, ge=1, description="Adults across all rooms.")
    children: int = Field(
        default=0, ge=0, description="Children across all rooms."
    )
    guest_name: str = Field(
        description="Full name of the lead guest as on their ID.",
        examples=["Nguyen Van A"],
    )
    guest_email: str = Field(
        description="Contact email for the reservation.",
        examples=["nguyen.a@example.com"],
    )
    guest_phone: str = Field(
        description="Contact phone for the hotel (late arrival, changes).",
        examples=["+84 901 234 567"],
    )
    notes: str | None = Field(
        default=None,
        description="Free-form note for the hotel — e.g. arrival time, bed preference.",
        examples=["Late arrival ~22:00"],
    )

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
