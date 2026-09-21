"""Reflection guard for the research launcher (Task 6.1, SC-19).

A turn that launched a deep-research job is terminal: reflection must END before
the judge, so a REVISE verdict can never route ``goto=current_flow`` ('research')
back into the launcher and start a second job. The launcher marks its reply with
``additional_kwargs={"research_started": True}``; the guard keys off that.

Unit tests drive the reflection node directly (``llm._cursor`` proves whether the
judge ran). One end-to-end test drives the whole graph with a stub service and
asserts ``start`` fires exactly once even though the judge says REVISE.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents import graph as graph_module
from app.agents.constants import RESEARCH_STARTED_MSG
from app.agents.context import AgentContext
from app.agents.graph import build_graph
from app.agents.nodes import _research_started_this_turn, make_reflection_node
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END
from langgraph.store.memory import InMemoryStore

OWNER = "u_research_guard"
TRIP = "trip-guard-1"


def _runtime(ctx: AgentContext | None = None) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def _started_msg() -> AIMessage:
    return AIMessage(
        content=RESEARCH_STARTED_MSG,
        additional_kwargs={"research_started": True},
    )


# -- the helper ---------------------------------------------------------------


def test_helper_true_only_for_a_started_reply_this_turn():
    started = [HumanMessage(content="research it"), _started_msg()]
    assert _research_started_this_turn(started) is True

    # A plain reply (no marker) does not trip the guard.
    plain = [HumanMessage(content="research it"), AIMessage(content="ok")]
    assert _research_started_this_turn(plain) is False

    # A marker from an EARLIER turn (before the last HumanMessage) does not guard.
    earlier = [
        HumanMessage(content="research it"),
        _started_msg(),
        HumanMessage(content="anything new?"),
        AIMessage(content="still working on it"),
    ]
    assert _research_started_this_turn(earlier) is False

    # A status reply (run already running/completed) is terminal too: a REVISE
    # would re-enter the launcher and emit the same reply twice.
    status = [
        HumanMessage(content="is my research done?"),
        AIMessage(content="done", additional_kwargs={"research_status": "completed"}),
    ]
    assert _research_started_this_turn(status) is True


# -- the reflection node ------------------------------------------------------


def test_research_launch_ends_the_turn_before_the_judge():
    llm = FakeLLM(responses=["REVISE this answer"])  # would loop if the judge ran
    reflect = make_reflection_node(llm)

    state = {
        "messages": [HumanMessage(content="research my trip"), _started_msg()],
        "revisions": 0,
        "current_flow": "research",
    }
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == END
    assert llm._cursor == 0  # the judge was never called → no REVISE, no re-launch


# -- end to end ---------------------------------------------------------------


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Seeded temp SQLite so load_context resolves a session; research_enabled on."""
    url = f"sqlite:///{tmp_path / 'research_guard.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


def test_graph_revise_after_research_launch_starts_one_job(agent_db, monkeypatch):
    # Stub the service the launcher node builds, so no real run is booked. ``launch``
    # is an AsyncMock because the node schedules it as an asyncio task after ``start``.
    service = MagicMock(name="ResearchService")
    service.runnable = True
    service.launch = AsyncMock(name="launch")
    monkeypatch.setattr(graph_module, "build_research_service", lambda store: service)

    main = FakeLLM(structured_responses=[SupervisorIntent(target_agent="research")])
    fast = FakeLLM(responses=["REVISE"])  # judge verdict — must never be consumed
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )

    out = asyncio.run(
        graph.ainvoke(
            {
                "messages": [HumanMessage(content="research my whole trip in depth")],
                "user_id": OWNER,
                "trip_id": TRIP,
            },
            {"configurable": {"thread_id": "t-research-guard"}},
        )
    )

    assert not out.get("__interrupt__")
    # The guard ended the turn before the judge ran, so the launcher fired ONCE.
    service.start.assert_called_once_with(OWNER, TRIP)
    assert fast._cursor == 0
    assert out.get("revisions", 0) == 0
    ai = [m for m in out["messages"] if isinstance(m, AIMessage)]
    assert ai[-1].content == RESEARCH_STARTED_MSG
