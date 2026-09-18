"""Read-only tool selection for the research agent and its subagents.

Reuses the existing registry — no tool is added or modified here, so ``/agent/manifest``
and the MCP surface stay byte-identical (non-replacement guarantee, SC-26).
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agents.constants import EPISODIC_TOOL_NAME
from app.tools.registry import ALL_TOOLS, TOOL_METADATA, get_tools_for

# Excluded from research even though read-only: cross-trip inventory listing, episodic
# recall, the raw preference dump, and the NL query parser (the deep agent reasons directly).
EXCLUDED: frozenset[str] = frozenset(
    {
        "list_trips",
        "recall_past_trips",
        "get_user_preferences",
        "parse_nl_query",
        EPISODIC_TOOL_NAME,
    }
)

_BY_NAME: dict[str, BaseTool] = {t.name: t for t in ALL_TOOLS}


def _resolve(names: list[str]) -> list[BaseTool]:
    for name in names:
        assert name in _BY_NAME, f"unknown tool in SUBAGENT_TOOLS: {name}"
    return [_BY_NAME[name] for name in names]


def research_tools() -> list[BaseTool]:
    """Planner ∪ concierge tools, read-only only, minus ``EXCLUDED``."""
    seen: dict[str, BaseTool] = {}
    for tool in get_tools_for("planner") + get_tools_for("concierge"):
        if tool.name in EXCLUDED:
            continue
        if not TOOL_METADATA[tool.name]["readOnly"]:
            continue
        seen[tool.name] = tool
    return list(seen.values())


# Per-dimension tool sets (design §3), resolved by name so a typo fails at import.
SUBAGENT_TOOLS: dict[str, list[BaseTool]] = {
    "flights": _resolve(["search_flights", "resolve_date"]),
    "stays": _resolve(
        [
            "search_hotels",
            "browse_hotels",
            "search_places",
            "nearby_places",
        ]
    ),
    "days": _resolve(
        [
            "search_places",
            "nearby_places",
            "resolve_place",
            "get_route",
            "get_city_route",
            "get_weather",
            "get_climate",
            "get_air_quality",
        ]
    ),
    "entry_season": _resolve(
        [
            "get_visa",
            "get_local_tips",
            "search_travel_knowledge",
            "get_climate",
            "get_packing",
        ]
    ),
    "budget": _resolve(
        [
            "get_trip_budget",
            "estimate_trip_budget",
            "expense_summary",
        ]
    ),
}
