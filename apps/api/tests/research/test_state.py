"""``ResearchState`` must survive the parent dispatching subagents concurrently."""

from __future__ import annotations

import pytest
from app.research.state import ResearchState
from langgraph.graph import END, START, StateGraph


def _two_writers_in_one_step() -> StateGraph:
    """A graph whose two parallel branches both write every forwarded key.

    This is the shape ``create_deep_agent`` produces when the model emits more
    than one ``task`` call in a turn: each subagent returns the run constants it
    was forwarded, so they land as concurrent writes in a single super-step.
    """
    graph = StateGraph(ResearchState)
    for name in ("flights", "stays"):
        graph.add_node(
            name,
            lambda _state: {
                "trip_id": "trip-1",
                "user_id": "user-1",
                "preferences": "quiet",
                "language": "vi",
            },
        )
        graph.add_edge(START, name)
        graph.add_edge(name, END)
    return graph


@pytest.mark.parametrize("key", ["trip_id", "user_id", "preferences", "language"])
def test_run_constants_tolerate_concurrent_subagent_writes(key: str) -> None:
    """Without a reducer these are ``LastValue`` channels and this raises
    ``InvalidUpdateError: At key '<key>': Can receive only one value per step``,
    which killed a real run mid-fan-out."""
    result = (
        _two_writers_in_one_step()
        .compile()
        .invoke(
            {
                "messages": [],
                "trip_id": "trip-1",
                "user_id": "user-1",
                "preferences": "quiet",
                "language": "vi",
            }
        )
    )

    assert (
        result[key]
        == {
            "trip_id": "trip-1",
            "user_id": "user-1",
            "preferences": "quiet",
            "language": "vi",
        }[key]
    )
