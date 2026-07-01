"""ORM models package. Reference via the namespace: `models.Hotel`, `models.Booking`.

Class names intentionally match app/schemas Pydantic models — disambiguate by import
(`from app.db import models` → models.X) vs (`from app.schemas.x import X`).
"""

from app.db.models.agent_config import AgentConfig
from app.db.models.airline import Airline
from app.db.models.airport import Airport
from app.db.models.booking import Booking
from app.db.models.city import City
from app.db.models.conversation import Conversation
from app.db.models.country import Country
from app.db.models.expense import Expense
from app.db.models.flight_index import FlightIndex
from app.db.models.fx import CountryCurrency, FxMeta, FxRate
from app.db.models.hotel import Hotel
from app.db.models.job import Job
from app.db.models.message import Message
from app.db.models.place import Place
from app.db.models.saved_place import SavedPlace
from app.db.models.tip import CountrySummary, Tip
from app.db.models.trip import Trip, TripItem, TripPlaceLink
from app.db.models.user import User
from app.db.models.visa import Visa

__all__ = [
    "AgentConfig",
    "Booking",
    "Conversation",
    "Message",
    "Job",
    "Expense",
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
    "Tip",
    "CountrySummary",
    "Visa",
    "FxRate",
    "CountryCurrency",
    "FxMeta",
    "User",
]
