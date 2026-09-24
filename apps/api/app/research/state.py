"""Research agent state — adds the channels the registry tools inject."""

from __future__ import annotations

from typing import Annotated, TypeVar

from deepagents import DeepAgentState

_T = TypeVar("_T")


def keep_run_constant(current: _T | None, incoming: _T | None) -> _T | None:
    """Reducer for a value fixed for the whole run.

    Without a reducer these are ``LastValue`` channels, which reject two writes
    in one step — and the parent dispatches several subagents concurrently, each
    returning the forwarded state. A live run died on
    ``InvalidUpdateError: At key 'trip_id': Can receive only one value per step``.
    Every writer writes the same value here, so collapsing them is safe.
    """
    return current if incoming is None else incoming


class ResearchState(DeepAgentState):
    """``DeepAgentState`` plus the ``InjectedState`` keys the registry tools read.

    ``search_flights``/``search_hotels`` inject ``preferences`` and ``language``;
    trip-scoped tools inject ``trip_id`` and ``user_id``. ``state_schema`` forwards
    these to declarative subagents so isolated subagents receive them too.
    """

    trip_id: Annotated[str, keep_run_constant]
    user_id: Annotated[str, keep_run_constant]
    preferences: Annotated[str, keep_run_constant]
    language: Annotated[str, keep_run_constant]
