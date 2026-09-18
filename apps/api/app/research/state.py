"""Research agent state — adds the channels the registry tools inject."""

from __future__ import annotations

from deepagents import DeepAgentState


class ResearchState(DeepAgentState):
    """``DeepAgentState`` plus the ``InjectedState`` keys the registry tools read.

    ``search_flights``/``search_hotels`` inject ``preferences`` and ``language``;
    trip-scoped tools inject ``trip_id`` and ``user_id``. ``state_schema`` forwards
    these to declarative subagents so isolated subagents receive them too.
    """

    trip_id: str
    user_id: str
    preferences: str
    language: str
