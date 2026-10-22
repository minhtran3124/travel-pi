"""Centralised string-valued enumerations — serialise transparently and compare equal to raw strings."""

from enum import Enum


class BookingType(str, Enum):
    """The kind of thing a booking refers to."""

    FLIGHT = "flight"
    HOTEL = "hotel"


class BookingStatus(str, Enum):
    """Lifecycle state of a booking; cancel is a soft state change — the row is kept."""

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
    """Sections of a destination overview response."""

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
    """Planning state of a trip itinerary item; ``booked`` here is planning state, independent of ``BookingStatus``."""

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
    """Spend buckets a per-trip budget cap can target; activities/buffer have no booking source yet so their spent is always 0."""

    FLIGHTS = "flights"
    HOTELS = "hotels"
    ACTIVITIES = "activities"
    BUFFER = "buffer"


class MessageRole(str, Enum):
    """Author role of a stored conversation message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class JobStatus(str, Enum):
    """Lifecycle of a long-running agent job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Tier(str, Enum):
    """BE-resolved account tier — the capability ceiling."""

    FREE = "free"
    PREMIUM = "premium"


class ResponseStyle(str, Enum):
    """How verbose a sub-agent reply should be — derived from the mode."""

    DEFAULT = "default"
    CONCISE = "concise"
    DETAILED = "detailed"


class FeedbackAction(str, Enum):
    """Kind of append-only ``feedback_events`` row."""

    SET_RATING = "set_rating"
    ADD_DETAIL = "add_detail"
    RETRACT_RATING = "retract_rating"


class FeedbackRating(int, Enum):
    """Thumbs value stored in ``feedback_events.rating``."""

    HELPFUL = 1
    NOT_HELPFUL = -1


class FeedbackReasonCode(str, Enum):
    """Allowlisted reasons a traveller can attach to a negative rating."""

    INCORRECT = "incorrect"
    IRRELEVANT = "irrelevant"
    INCOMPLETE = "incomplete"
    UNSAFE = "unsafe"
    OTHER = "other"


class FeedbackSource(str, Enum):
    """UI surface that produced a feedback event."""

    CHAT_MESSAGE_ACTIONS = "chat_message_actions"
