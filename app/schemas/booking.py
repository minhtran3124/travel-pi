"""Booking schema, shared by flight and hotel bookings."""

from datetime import datetime

from app.enums import BookingStatus, BookingType
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class Booking(AppBaseModel):
    """A confirmed flight or hotel booking."""

    id: str
    type: BookingType
    reference_id: str  # The flight_id or hotel_id
    customer_name: str
    customer_email: str
    total_price: float
    currency: str = "USD"
    status: BookingStatus = BookingStatus.CONFIRMED
    created_at: datetime
    details: dict  # Type-specific payload (see endpoint specs)
    notes: str | None = None  # Optional agent/user context


class BookingListResponse(PagedResponse[Booking]):
    """Response body for ``GET /bookings``."""
