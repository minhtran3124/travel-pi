"""Checkpointer selection + persistence (specs/travel-agent Task 2.1;
agent-graph-lifecycle — Postgres-only durable backend, async, in-memory degrade)."""

import asyncio
import operator
from typing import Annotated

import pytest
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


def test_open_checkpointer_degrades_with_warning_when_postgres_unreachable(caplog):
    """A *configured* Postgres that can't connect degrades to MemorySaver in dev/test,
    but loudly — the warning is what stops the swap from being silent (the trap that
    made conversation history vanish on restart)."""
    from app.agents.checkpointer import open_checkpointer

    bad = "postgresql+psycopg://x:x@127.0.0.1:5999/none"

    async def _resolve():
        async with open_checkpointer(bad) as cp:
            return cp

    with caplog.at_level("WARNING"):
        cp = asyncio.run(_resolve())
    assert isinstance(cp, MemorySaver)
    assert "EPHEMERAL" in caplog.text


def test_open_checkpointer_fails_fast_in_production(monkeypatch):
    """In production a configured-but-unreachable Postgres must raise, never degrade to
    an ephemeral checkpointer that silently loses conversation history."""
    import app.agents.checkpointer as cpmod

    class _ProdSettings:
        is_production = True

    monkeypatch.setattr(cpmod, "get_settings", lambda: _ProdSettings())
    bad = "postgresql+psycopg://x:x@127.0.0.1:5999/none"

    async def _resolve():
        async with cpmod.open_checkpointer(bad) as cp:
            return cp

    with pytest.raises(Exception):
        asyncio.run(_resolve())


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
