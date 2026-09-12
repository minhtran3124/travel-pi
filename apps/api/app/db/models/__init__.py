"""ORM models package. Reference via the namespace: `models.Hotel`, `models.Booking`.

Class names intentionally match app/schemas Pydantic models — disambiguate by import
(`from app.db import models` → models.X) vs (`from app.schemas.x import X`).
"""

from app.db.models.agent_config import AgentConfig
from app.db.models.agent_run import AgentRun
from app.db.models.agent_run_step import AgentRunStep
from app.db.models.airline import Airline
from app.db.models.airport import Airport
from app.db.models.booking import Booking
from app.db.models.city import City
from app.db.models.content_translation import ContentTranslation
from app.db.models.conversation import Conversation
from app.db.models.country import Country
from app.db.models.expense import Expense
from app.db.models.feedback_event import FeedbackEvent
from app.db.models.flight_index import FlightIndex
from app.db.models.fx import CountryCurrency, FxMeta, FxRate
from app.db.models.hotel import Hotel
from app.db.models.job import Job
from app.db.models.message import Message
from app.db.models.place import Place
from app.db.models.rate_limit_counter import RateLimitCounter
from app.db.models.saved_place import SavedPlace
from app.db.models.tip import CountrySummary, Tip
from app.db.models.trip import Trip, TripItem, TripPlaceLink
from app.db.models.user import User
from app.db.models.visa import Visa

__all__ = [
    "AgentConfig",
    "AgentRun",
    "AgentRunStep",
    "Booking",
    "ContentTranslation",
    "Conversation",
    "Message",
    "Job",
    "Expense",
    "FeedbackEvent",
    "Trip",
    "TripItem",
    "TripPlaceLink",
    "SavedPlace",
    "FlightIndex",
    "Country",
    "Airline",
    "Airport",
    "City",
    "Hotel",
    "Place",
    "RateLimitCounter",
    "Tip",
    "CountrySummary",
    "Visa",
    "FxRate",
    "CountryCurrency",
    "FxMeta",
    "User",
]
