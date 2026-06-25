"""Checkpointer selection + persistence (specs/travel-agent Task 2.1)."""

import operator
from typing import Annotated

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


def test_sqlite_url_returns_sqlite_saver():
    from app.agents.checkpointer import get_checkpointer

    cp = get_checkpointer("sqlite:///:memory:")
    assert isinstance(cp, SqliteSaver)


def test_unknown_url_falls_back_to_memory():
    from app.agents.checkpointer import get_checkpointer

    cp = get_checkpointer("redis://nope")
    assert isinstance(cp, MemorySaver)


def test_state_persists_across_invocations_by_thread_id():
    from app.agents.checkpointer import get_checkpointer

    # `add` reducer so persisted state accumulates across invocations — that is
    # what proves the checkpointer is resuming, not just re-running from scratch.
    class S(TypedDict):
        count: Annotated[int, operator.add]

    def bump(state: S) -> S:
        return {"count": 1}

    g = StateGraph(S)
    g.add_node("bump", bump)
    g.add_edge(START, "bump")
    g.add_edge("bump", END)
    graph = g.compile(checkpointer=get_checkpointer("sqlite:///:memory:"))

    cfg = {"configurable": {"thread_id": "user_1_trip_1"}}
    assert graph.invoke({"count": 0}, cfg)["count"] == 1
    out = graph.invoke({"count": 0}, cfg)  # resumes persisted count (1) -> 2
    assert out["count"] == 2

    # a different thread starts fresh
    other = graph.invoke({"count": 0}, {"configurable": {"thread_id": "user_2"}})
    assert other["count"] == 1
