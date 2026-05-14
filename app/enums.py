"""Centralised enumerations.

String-valued enums so they serialise transparently in JSON and compare
equal to the raw strings used in query params and the SQLite store, while
giving the codebase a single source of truth for the valid values.
"""

from enum import Enum


class BookingType(str, Enum):
    """The kind of thing a booking refers to."""

    FLIGHT = "flight"
    HOTEL = "hotel"


class BookingStatus(str, Enum):
    """Lifecycle state of a booking. The mock only ever creates confirmed ones."""

    CONFIRMED = "confirmed"


class BookingSort(str, Enum):
    """Sort orders accepted by ``GET /bookings``."""

    CREATED_DESC = "created_desc"
    CREATED_ASC = "created_asc"
    PRICE_DESC = "price_desc"
    PRICE_ASC = "price_asc"
