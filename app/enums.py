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
    """Lifecycle state of a booking.

    New bookings are always ``CONFIRMED``; ``POST /bookings/{id}/cancel``
    moves them to ``CANCELLED`` (a soft state change — the row is kept).
    """

    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class BookingSort(str, Enum):
    """Sort orders accepted by ``GET /bookings``."""

    CREATED_DESC = "created_desc"
    CREATED_ASC = "created_asc"
    PRICE_DESC = "price_desc"
    PRICE_ASC = "price_asc"


class FlightSort(str, Enum):
    """Sort orders accepted by ``GET /flights/search``."""

    DEPARTURE_ASC = "departure_asc"
    DEPARTURE_DESC = "departure_desc"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    DURATION_ASC = "duration_asc"
    DURATION_DESC = "duration_desc"


class PlaceCategory(str, Enum):
    """Categories a place can fall into."""

    ATTRACTION = "attraction"
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    ACTIVITY = "activity"
    NIGHTLIFE = "nightlife"
    SHOPPING = "shopping"


class PlaceSort(str, Enum):
    """Sort orders accepted by ``GET /places/search``."""

    RATING_DESC = "rating_desc"
    RATING_ASC = "rating_asc"
    NAME = "name"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    REVIEWS_DESC = "reviews_desc"


class TipCategory(str, Enum):
    """Categories the tip catalog organises advice into."""

    TRANSPORT = "transport"
    MONEY = "money"
    SAFETY = "safety"
    CULTURE = "culture"
    FOOD = "food"
    CONNECTIVITY = "connectivity"
    HEALTH = "health"
    ETIQUETTE = "etiquette"
    BEST_TIME = "best_time"
    LANGUAGE = "language"
