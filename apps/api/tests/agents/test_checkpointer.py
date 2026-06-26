"""Checkpointer selection + persistence (specs/travel-agent Task 2.1;
agent-graph-lifecycle — Postgres-only durable backend, async, in-memory degrade)."""

import asyncio
import operator
from typing import Annotated

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


def test_get_checkpointer_returns_memory_saver():
    """The sync helper is the ephemeral in-memory path (tests / non-Postgres degrade)."""
    from app.agents.checkpointer import get_checkpointer

    assert isinstance(get_checkpointer(), MemorySaver)
    assert isinstance(get_checkpointer("sqlite:///:memory:"), MemorySaver)


def test_open_checkpointer_degrades_to_memory_off_postgres():
    """Non-Postgres URLs yield a MemorySaver so local/test runs start without Postgres."""
    from app.agents.checkpointer import open_checkpointer

    async def _resolve():
        async with open_checkpointer("sqlite:///:memory:") as cp:
            return cp

    assert isinstance(asyncio.run(_resolve()), MemorySaver)


def test_libpq_dsn_strips_sqlalchemy_driver():
    """The async Postgres saver needs a libpq DSN, not the SQLAlchemy +psycopg form."""
    from app.agents.checkpointer import _libpq_dsn

    assert (
        _libpq_dsn("postgresql+psycopg://u:p@db:5432/x") == "postgresql://u:p@db:5432/x"
    )


def test_state_persists_across_invocations_by_thread_id():
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
    graph = g.compile(checkpointer=MemorySaver())

    cfg = {"configurable": {"thread_id": "user_1_trip_1"}}
    assert graph.invoke({"count": 0}, cfg)["count"] == 1
    out = graph.invoke({"count": 0}, cfg)  # resumes persisted count (1) -> 2
    assert out["count"] == 2

    # a different thread starts fresh
    other = graph.invoke({"count": 0}, {"configurable": {"thread_id": "user_2"}})
    assert other["count"] == 1
