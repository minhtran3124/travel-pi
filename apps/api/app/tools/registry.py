"""Tool registry (specs/travel-agent Task 3.4).

Single source of truth for the agent's tools. ``get_tools_for(domain)`` returns
the tool group bound to a sub-agent so we bind only the relevant tools per turn
(avoids tool sprawl). ``TOOL_METADATA`` carries MCP-style readOnly/destructive
annotations (roadmap B1) surfaced by ``/agent/manifest`` and the MCP server.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.tools.expense_tools import EXPENSE_TOOLS
from app.tools.flight_tools import FLIGHT_TOOLS
from app.tools.hotel_tools import HOTEL_SEARCH_TOOLS, HOTEL_TOOLS
from app.tools.memory_tools import EPISODE_TOOLS, MEMORY_TOOLS
from app.tools.place_tools import PLACE_TOOLS
from app.tools.rag_tools import KNOWLEDGE_TOOLS
from app.tools.routing_tools import ROUTING_TOOLS
from app.tools.tip_tools import TIP_TOOLS
from app.tools.trip_tools import TRIP_TOOLS
from app.tools.weather_tools import WEATHER_TOOLS

# Tools grouped by the sub-agent that should bind them.
TOOLS_BY_DOMAIN: dict[str, list[BaseTool]] = {
    "planner": (
        TRIP_TOOLS
        + PLACE_TOOLS
        + FLIGHT_TOOLS
        + HOTEL_TOOLS
        + WEATHER_TOOLS
        + ROUTING_TOOLS
        + EPISODE_TOOLS
    ),
    "concierge": (
        PLACE_TOOLS
        + WEATHER_TOOLS
        + ROUTING_TOOLS
        + TIP_TOOLS
        + HOTEL_SEARCH_TOOLS
        + KNOWLEDGE_TOOLS
    ),
    "journal": TRIP_TOOLS + MEMORY_TOOLS,
    "booking": FLIGHT_TOOLS + HOTEL_TOOLS,
    "budget": EXPENSE_TOOLS + [t for t in TRIP_TOOLS if t.name == "get_trip_budget"],
}

# Every distinct tool, de-duplicated by name (a tool may appear in >1 domain).
ALL_TOOLS: list[BaseTool] = list(
    {t.name: t for group in TOOLS_BY_DOMAIN.values() for t in group}.values()
)

# MCP-style annotations per tool name. readOnly=True => safe GET-like call;
# destructive=True => irreversible side effect (money / cancellation).
_DESTRUCTIVE = {"book_hotel"}
_WRITE = {
    "add_place_to_trip",
    "add_itinerary_item",
    "add_expense",
    "save_user_preference",
    "book_hotel",
}


def _meta(name: str) -> dict[str, bool]:
    return {
        "readOnly": name not in _WRITE,
        "destructive": name in _DESTRUCTIVE,
    }


TOOL_METADATA: dict[str, dict[str, bool]] = {t.name: _meta(t.name) for t in ALL_TOOLS}


def get_tools_for(domain: str) -> list[BaseTool]:
    """Return the tool group for a sub-agent domain (empty list if unknown).

    :param domain: The sub-agent domain name (e.g. 'planner', 'concierge').
    :return: The tools bound to that domain.
    """
    return TOOLS_BY_DOMAIN.get(domain, [])
