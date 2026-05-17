"""Booking schema, shared by flight and hotel bookings."""

import hashlib
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, computed_field

from app.enums import BookingStatus, BookingType
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse

# Confirmation-code alphabet: uppercase letters + digits, minus the
# visually ambiguous ones (0/O, 1/I/L) — the same trick real airlines and
# hotels use to keep a reference readable when typed or read aloud.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6


def confirmation_code_for(booking_id: str) -> str:
    """Derive a stable 6-char PNR-style confirmation code from a booking ID.

    Real airlines/GDS issue a 6-character alphanumeric *record locator* (PNR),
    and hotels a similar *confirmation number* — far friendlier than a raw
    UUID. We derive it deterministically from the UUID so it needs no extra
    storage and never drifts: the same booking always has the same code.
    """
    digest = hashlib.sha256(booking_id.encode()).digest()
    number = int.from_bytes(digest[:8], "big")
    chars = []
    for _ in range(_CODE_LENGTH):
        number, index = divmod(number, len(_CODE_ALPHABET))
        chars.append(_CODE_ALPHABET[index])
    return "".join(chars)


def _trim_iso(value: str) -> str:
    """'2026-06-01T08:30:00' -> '2026-06-01 08:30' (best-effort, never raises)."""
    return value[:16].replace("T", " ") if isinstance(value, str) else str(value)


class FlightBookingDetails(AppBaseModel):
    """Flight-specific payload stored on a ``Booking``.

    The ``kind`` discriminator lets ``Booking.details`` be a tagged union so
    OpenAPI / FE codegen produce a real ``FlightBookingDetails | HotelBookingDetails``
    type instead of an untyped object.
    """

    kind: Literal["flight"] = "flight"
    flight_id: str
    flight_number: str
    airline: str
    origin: str
    destination: str
    departure_time: str  # ISO 8601
    arrival_time: str  # ISO 8601
    passenger_name: str
    passenger_phone: str | None = None


class HotelBookingDetails(AppBaseModel):
    """Hotel-specific payload stored on a ``Booking``."""

    kind: Literal["hotel"] = "hotel"
    hotel_id: str
    hotel_name: str
    city: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    nights: int
    rooms: int
    adults: int
    children: int
    price_per_night: float
    guest_phone: str | None = None


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

    id: str
    type: BookingType
    reference_id: str  # The flight_id or hotel_id
    customer_name: str
    customer_email: str
    total_price: float
    currency: str = "USD"
    status: BookingStatus = BookingStatus.CONFIRMED
    created_at: datetime
    details: BookingDetails
    notes: str | None = None  # Optional agent/user context

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
