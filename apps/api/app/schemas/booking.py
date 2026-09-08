"""Booking schema, shared by flight and hotel bookings."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, computed_field

from app.core.codes import short_code_for
from app.enums import BookingStatus, BookingType
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


def confirmation_code_for(booking_id: str) -> str:
    """Derive a stable 6-char PNR-style confirmation code from a booking ID.

    Real airlines/GDS issue a 6-character alphanumeric *record locator* (PNR),
    and hotels a similar *confirmation number* — far friendlier than a raw
    UUID. We derive it deterministically from the UUID so it needs no extra
    storage and never drifts: the same booking always has the same code.
    """
    return short_code_for(booking_id)


def _trim_iso(value: str) -> str:
    """'2026-06-01T08:30:00' -> '2026-06-01 08:30' (best-effort, never raises)."""
    return value[:16].replace("T", " ") if isinstance(value, str) else str(value)


class FlightBookingDetails(AppBaseModel):
    """Flight-specific payload stored on a ``Booking``.

    The ``kind`` discriminator lets ``Booking.details`` be a tagged union so
    OpenAPI / FE codegen produce a real ``FlightBookingDetails | HotelBookingDetails``
    type instead of an untyped object.
    """

    kind: Literal["flight"] = Field(
        default="flight",
        description="Tag for the discriminated union — always 'flight' here.",
    )
    flight_id: str = Field(description="The canonical flight_id booked.")
    flight_number: str = Field(description="Airline + number, e.g. 'VN123'.")
    airline: str = Field(description="Marketing name of the airline.")
    origin: str = Field(description="IATA origin code.")
    destination: str = Field(description="IATA destination code.")
    departure_time: str = Field(description="Scheduled departure time, ISO 8601.")
    arrival_time: str = Field(description="Scheduled arrival time, ISO 8601.")
    passenger_name: str = Field(description="Name on the ticket.")
    passenger_phone: str | None = Field(default=None, description="Contact phone.")


class HotelBookingDetails(AppBaseModel):
    """Hotel-specific payload stored on a ``Booking``."""

    kind: Literal["hotel"] = Field(
        default="hotel",
        description="Tag for the discriminated union — always 'hotel' here.",
    )
    hotel_id: str = Field(description="The hotel ID booked.")
    hotel_name: str = Field(description="Hotel name at the time of booking.")
    city: str = Field(description="City the hotel is in.")
    check_in: str = Field(description="Check-in date, YYYY-MM-DD.")
    check_out: str = Field(description="Check-out date, YYYY-MM-DD.")
    nights: int = Field(description="Stay length, in nights.")
    rooms: int = Field(description="Rooms booked.")
    adults: int = Field(description="Adults in the party.")
    children: int = Field(description="Children in the party.")
    price_per_night: float = Field(description="Locked nightly rate at booking time.")
    guest_phone: str | None = Field(
        default=None, description="Contact phone for the hotel."
    )


BookingDetails = Annotated[
    FlightBookingDetails | HotelBookingDetails,
    Field(discriminator="kind"),
]


def build_summary(
    booking_type: BookingType, customer_name: str, details: BookingDetails
) -> str:
    """Build a one-line, human-readable description of a booking.

    Agents (and people) shouldn't have to dig through ``details`` to know
    what a booking *is* — this is the at-a-glance version.
    """
    if booking_type == BookingType.FLIGHT and isinstance(details, FlightBookingDetails):
        return (
            f"{details.airline} {details.flight_number} · "
            f"{details.origin}→{details.destination} · "
            f"departs {_trim_iso(details.departure_time)} · "
            f"{customer_name}"
        )
    assert isinstance(details, HotelBookingDetails)
    guests = (details.adults + details.children) or "?"
    return (
        f"{details.hotel_name}, {details.city} · "
        f"{details.check_in}→{details.check_out} "
        f"({details.nights} night{'s' if details.nights != 1 else ''}) · "
        f"{details.rooms} room{'s' if details.rooms != 1 else ''}, {guests} guest"
        f"{'s' if guests != 1 else ''} · {customer_name}"
    )


class Booking(AppBaseModel):
    """A confirmed flight or hotel booking.

    ``id`` is the canonical UUID (stable, used in URLs); ``confirmation_code``
    is the friendly 6-character reference a human or agent would actually
    quote — either can be passed to ``GET /bookings/{id}``.
    """

    id: str = Field(
        description="Canonical booking UUID. Accepted by /bookings/{id}.",
        examples=["c1e1f5a4-ce3a-5b24-8f2e-8a0a8b3c2c5a"],
    )
    type: BookingType = Field(description="Booking kind — 'flight' or 'hotel'.")
    reference_id: str = Field(
        description="The flight_id or hotel_id this booking references."
    )
    customer_name: str = Field(description="Name on the booking (passenger or guest).")
    customer_email: str = Field(description="Contact email for the booking.")
    total_price: float = Field(
        description=(
            "Server-computed total: flight fare for flights; "
            "price_per_night × nights × rooms for hotels."
        )
    )
    currency: str = Field(default="USD", description="ISO 4217 currency code.")
    status: BookingStatus = Field(
        default=BookingStatus.CONFIRMED,
        description="'confirmed' (default) or 'cancelled' after /cancel.",
    )
    created_at: datetime = Field(description="When the booking was created (UTC).")
    details: BookingDetails
    notes: str | None = Field(
        default=None,
        description="Free-form note an agent or user attached at booking time.",
    )
    trip_id: str | None = Field(
        default=None,
        description="The trip this booking is attached to, if any.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confirmation_code(self) -> str:
        """Friendly 6-char PNR-style reference, derived from ``id``."""
        return confirmation_code_for(self.id)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> str:
        """One-line human-readable description of this booking."""
        return build_summary(self.type, self.customer_name, self.details)


class BookingListResponse(PagedResponse[Booking]):
    """Response body for ``GET /bookings``."""
