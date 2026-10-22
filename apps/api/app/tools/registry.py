"""Single source of truth for the agent's tools, grouped by sub-agent domain."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.core.config import get_settings
from app.tools.booking_tools import BOOKING_TOOLS
from app.tools.climate_tools import CLIMATE_TOOLS
from app.tools.date_tools import DATE_TOOLS
from app.tools.expense_tools import EXPENSE_TOOLS
from app.tools.flight_tools import FLIGHT_SEARCH_TOOLS, FLIGHT_TOOLS
from app.tools.hotel_tools import (
    HOTEL_AVAILABILITY_TOOLS,
    HOTEL_SEARCH_TOOLS,
    HOTEL_TOOLS,
)
from app.tools.memory_tools import EPISODE_TOOLS, MEMORY_TOOLS
from app.tools.place_tools import PLACE_TOOLS
from app.tools.rag_tools import KNOWLEDGE_TOOLS
from app.tools.routing_tools import ROUTING_TOOLS
from app.tools.tip_tools import TIP_TOOLS
from app.tools.trip_tools import (
    TRIP_TOOLS,
    create_trip,
    estimate_trip_budget,
    set_trip_budget,
)
from app.tools.visa_tools import VISA_TOOLS
from app.tools.weather_tools import WEATHER_TOOLS
from app.tools.web_search_tools import WEB_SEARCH_TOOLS

TOOLS_BY_DOMAIN: dict[str, list[BaseTool]] = {
    # Planner searches but never books: the money tools live only in the HITL-gated booking domain.
    "planner": (
        TRIP_TOOLS
        + [create_trip]
        + PLACE_TOOLS
        + FLIGHT_SEARCH_TOOLS
        + HOTEL_AVAILABILITY_TOOLS
        + WEATHER_TOOLS
        + CLIMATE_TOOLS
        + ROUTING_TOOLS
        + EPISODE_TOOLS
        + DATE_TOOLS
    ),
    "concierge": (
        PLACE_TOOLS
        + WEATHER_TOOLS
        + CLIMATE_TOOLS
        + ROUTING_TOOLS
        + TIP_TOOLS
        + VISA_TOOLS
        + HOTEL_SEARCH_TOOLS
        + HOTEL_AVAILABILITY_TOOLS
        + KNOWLEDGE_TOOLS
        + DATE_TOOLS
        + WEB_SEARCH_TOOLS
    ),
    "journal": TRIP_TOOLS + MEMORY_TOOLS,
    "booking": FLIGHT_TOOLS + HOTEL_TOOLS + BOOKING_TOOLS + DATE_TOOLS,
    "budget": (
        EXPENSE_TOOLS
        + [t for t in TRIP_TOOLS if t.name in {"get_trip_budget", "get_trip_summary"}]
        + [estimate_trip_budget, set_trip_budget]
    ),
}

# Every distinct tool, de-duplicated by name (a tool may appear in >1 domain).
ALL_TOOLS: list[BaseTool] = list(
    {t.name: t for group in TOOLS_BY_DOMAIN.values() for t in group}.values()
)

_DESTRUCTIVE = {"book_hotel", "book_flight", "cancel_flight", "cancel_hotel"}
_WRITE = {
    "add_place_to_trip",
    "add_itinerary_item",
    "add_expense",
    "save_user_preference",
    "book_hotel",
    "book_flight",
    "cancel_flight",
    "cancel_hotel",
    "create_trip",
    "set_trip_budget",
}


def _meta(name: str) -> dict[str, bool]:
    return {
        "readOnly": name not in _WRITE,
        "destructive": name in _DESTRUCTIVE,
    }


TOOL_METADATA: dict[str, dict[str, bool]] = {t.name: _meta(t.name) for t in ALL_TOOLS}


_SERPAPI_TOOLS = {"find_places_live"}


def available(tools: list[BaseTool]) -> list[BaseTool]:
    """Drop web-search tools whose provider is unavailable, read at call time.

    ``search_web`` needs Tavily; ``find_places_live`` needs SerpAPI.
    Settings are read here (not at import) so a flag/key change takes effect on the
    next graph build without a re-import.
    """
    settings = get_settings()
    tavily_ok = settings.tavily_search_available
    serpapi_ok = settings.serpapi_search_available
    return [
        t
        for t in tools
        if not (t.name == "search_web" and not tavily_ok)
        and not (t.name in _SERPAPI_TOOLS and not serpapi_ok)
    ]


def get_tools_for(domain: str) -> list[BaseTool]:
    """Return the available tool group for a sub-agent domain (empty if unknown)."""
    return available(TOOLS_BY_DOMAIN.get(domain, []))
