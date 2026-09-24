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

# Identifiers the RUN owns and the model cannot know. A research run is started for
# one trip by one owner; inside it the model has no legitimate way to learn either id,
# so a tool that asks for one can only be answered with a guess — which is exactly what
# happened on the first live run (a subagent invented ``trip_id="current"`` and the turn
# died on ``Trip 'current' not found``). Registry tools normally take these through
# ``InjectedState``, invisible to the model; one did not.
_RUN_OWNED_IDS: frozenset[str] = frozenset({"trip_id", "user_id"})

_BY_NAME: dict[str, BaseTool] = {t.name: t for t in ALL_TOOLS}


def _assert_bindable(tool: BaseTool) -> None:
    """Reject a tool the research agent must not bind, at import rather than mid-run."""
    asked = _RUN_OWNED_IDS & set(tool.args)
    assert not asked, (
        f"{tool.name} exposes {sorted(asked)} to the model; inside a research run the "
        "model cannot know them and will invent a value. Bind a tool that takes them "
        "through InjectedState, or leave it out."
    )
    assert tool.name not in EXCLUDED, f"{tool.name} is excluded from research"
    assert TOOL_METADATA[tool.name]["readOnly"], f"{tool.name} is not read-only"


def _resolve(names: list[str]) -> list[BaseTool]:
    """Resolve subagent tool names against the registry under the same rules the
    parent's pool obeys — a subagent must not reach past the parent's filter."""
    for name in names:
        assert name in _BY_NAME, f"unknown tool in SUBAGENT_TOOLS: {name}"
        _assert_bindable(_BY_NAME[name])
    return [_BY_NAME[name] for name in names]


def research_tools() -> list[BaseTool]:
    """Planner ∪ concierge tools, read-only only, minus ``EXCLUDED``."""
    seen: dict[str, BaseTool] = {}
    for tool in get_tools_for("planner") + get_tools_for("concierge"):
        if tool.name in EXCLUDED:
            continue
        if not TOOL_METADATA[tool.name]["readOnly"]:
            continue
        _assert_bindable(tool)
        seen[tool.name] = tool
    return list(seen.values())


# The main agent's own tools (design §2): the trip summary is its only source for the
# destination, dates and party — a Research-tab run starts with a generic instruction.
MAIN_TOOLS: list[BaseTool] = _resolve(["get_trip_summary"])

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
            "search_web",
            "find_places_live",
        ]
    ),
    "entry_season": _resolve(
        [
            "get_visa",
            "get_local_tips",
            "search_travel_knowledge",
            "get_climate",
            "get_packing",
            "search_web",
        ]
    ),
    # ``expense_summary`` is deliberately absent: it takes ``trip_id`` from the MODEL
    # rather than from state, and this agent is built once and shared across trips, so
    # there is no build-time value to bind. ``get_trip_budget`` already gives the trip's
    # caps through InjectedState.
    "budget": _resolve(
        [
            "get_trip_budget",
            "estimate_trip_budget",
        ]
    ),
}
