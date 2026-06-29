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


class OverviewSection(str, Enum):
    """Sections of a destination overview response.

    Pass one or more via ``?include=weather&include=places`` to restrict
    which sections are returned. Omit the param to get all four.
    """

    WEATHER = "weather"
    PLACES = "places"
    TIPS = "tips"
    HOTELS = "hotels"


class TripItemKind(str, Enum):
    """The kind of entry in a trip itinerary's day plan."""

    PLACE = "place"
    ACTIVITY = "activity"
    MEAL = "meal"
    TRANSPORT = "transport"
    NOTE = "note"


class TripItemStatus(str, Enum):
    """Planning state of a trip itinerary item.

    Lets an agent express soft vs. hard plan and hard constraints:
    ``pending`` (default, not yet decided), ``booked`` (locked in — note this
    is the *planning* state and is independent of ``BookingStatus`` /
    ``booking_id``), ``constraint`` (a fixed must-happen anchor), and
    ``optional`` (nice-to-have; excluded from gap-detection).
    """

    PENDING = "pending"
    BOOKED = "booked"
    CONSTRAINT = "constraint"
    OPTIONAL = "optional"


class MealStyle(str, Enum):
    """Meal-spend tier for a trip budget estimate."""

    BUDGET = "budget"
    MID = "mid"
    FINE = "fine"


class ActivityLevel(str, Enum):
    """Activity-spend tier for a trip budget estimate."""

    NONE = "none"
    SOME = "some"
    LOTS = "lots"


class ExpenseCategory(str, Enum):
    """Categories for on-trip expense ledger entries."""

    FOOD = "food"
    TRANSPORT = "transport"
    ACCOMMODATION = "accommodation"
    ACTIVITIES = "activities"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    HEALTH = "health"
    OTHER = "other"


class BudgetCategory(str, Enum):
    """Spend buckets a per-trip budget cap can target.

    flights/hotels map 1:1 to BookingType; activities/buffer have no booking
    source yet (activity booking is unshipped, #15) so their spent is always 0.
    """

    FLIGHTS = "flights"
    HOTELS = "hotels"
    ACTIVITIES = "activities"
    BUFFER = "buffer"


class MessageRole(str, Enum):
    """Author role of a stored conversation message (specs/travel-agent)."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class JobStatus(str, Enum):
    """Lifecycle of a long-running agent job (specs/travel-agent)."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ChatMode(str, Enum):
    """User-selectable response mode — the depth lever (specs/agent-mode-tier).

    Maps to a concrete capability set in ``resolve_agent_context``; unknown
    values fall back to ``BALANCED``.
    """

    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


class Tier(str, Enum):
    """BE-resolved account tier — the capability ceiling (specs/agent-identity-tier)."""

    FREE = "free"
    PREMIUM = "premium"


class ResponseStyle(str, Enum):
    """How verbose a sub-agent reply should be — derived from the mode."""

    DEFAULT = "default"
    CONCISE = "concise"
    DETAILED = "detailed"


class ModelHint(str, Enum):
    """Semantic model-tier hint carried by ``AgentContext.model``.

    ``None`` (no hint) means the per-agent default; ``FAST``/``DEEP`` force a
    tier in ``get_agent_llm``.
    """

    FAST = "fast"
    DEEP = "deep"
