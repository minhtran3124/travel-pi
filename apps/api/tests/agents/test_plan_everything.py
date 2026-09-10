"""Plan-everything golden — a dependent chain routes to ONE specialist that runs
the whole tool chain in its own ReAct loop (specs/multi-intent-single-path, SC-6).

Option A collapses the two multi-intent mechanisms into one parallel model: the
supervisor emits a deduplicated ``tasks`` list, ``route_tasks`` fans genuinely
independent slices out to ``synthesis_worker`` instances, and a dependent chain
(flights → hotel → places → weather → itinerary — all planner-owned tools) routes
to the single ``planner`` specialist, whose own loop is the sequential executor.

This module proves two things for the flagship "plan everything" request:

- **Topology** — ``plan=["concierge"]`` yields exactly ONE planner task and ONE
  concierge task (no duplicate planner), and a single synthesized answer.
- **Recursion budget** — the planner runs a 7-tool chain in its own ReAct loop.
  Because each ``synthesis_worker`` invokes its inner specialist subgraph with the
  parent's ``config`` (so the inner graph inherits ``recursion_limit``), that loop
  must fit under ``agent_recursion_limit`` (25). The second test MEASURES the
  planner loop's super-step count and asserts it fits with headroom.

Hermetic: ``agent_db`` points DATABASE_URL at a seeded temp SQLite DB so the real
planner tools run; the one networked tool (``get_weather``) is stubbed to a
deterministic domain error so the loop stays offline (the tool still returns a
ToolMessage — only the network is removed).

The two parallel synthesis workers share the single injected main model, so a
plain cursor-based FakeLLM would race (each worker runs on its own thread). The
test-local :class:`_AgentAwareLLM` routes scripted responses per specialist by
inspecting the system prompt, keeping each specialist's script independent.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from app.agents.context import AgentContext
from app.agents.graph import build_graph
from app.agents.subagents.planner import build_planner
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.exceptions import CityNotFoundError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import PrivateAttr


def _drive(graph, *args, **kwargs):
    """Run the graph the way production does — asynchronously.

    ``synthesis_worker`` is an async node (#178: the specialists bind async-only
    tools), and a sync ``graph.invoke`` cannot execute one. Production always uses
    ``ainvoke``/``astream``, so driving the graph this way is also the more
    faithful test.
    """
    return asyncio.run(graph.ainvoke(*args, **kwargs))


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Point DATABASE_URL at a fresh seeded temp SQLite DB so the real planner
    tools run in-graph (they resolve their session from the setting, not a
    request). Mirrors ``tests/tools/conftest.agent_db``; kept local so this
    module is self-contained and free of a cross-package fixture import."""
    url = f"sqlite:///{tmp_path / 'plan_everything.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


def _tc(name: str, **args: Any) -> AIMessage:
    """A scripted assistant turn that calls one tool."""
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": f"{name}-call"}]
    )


# The planner's dependent chain: flights → hotel → places → weather → create the
# trip → two itinerary items → final prose. Seven tool rounds, all planner-owned
# tools, then one content-bearing answer that ends the ReAct loop.
_PLANNER_SCRIPT: list[AIMessage] = [
    _tc("search_flights", origin="DAD", destination="SGN", departure_date="2026-12-01"),
    _tc(
        "search_hotels",
        city="Tokyo",
        check_in="2026-12-01",
        check_out="2026-12-03",
        rooms=1,
        adults=2,
        children=0,
    ),
    _tc("search_places", city="Tokyo"),
    _tc("get_weather", city="Tokyo"),
    _tc("create_trip", title="Tokyo weekend"),
    _tc("add_itinerary_item", day=1, title="Sensō-ji temple"),
    _tc("add_itinerary_item", day=2, title="Shibuya crossing"),
    AIMessage(content="Here is your Tokyo weekend itinerary, day by day."),
]
_CONCIERGE_SCRIPT: list[AIMessage] = [
    AIMessage(content="Local tip: grab a Suica card for trains and konbini.")
]
_SYNTHESIZE_SCRIPT: list[AIMessage] = [
    AIMessage(content="Your Tokyo weekend is planned — flights, hotel, places, tips.")
]


class _AgentAwareLLM(BaseChatModel):
    """A scripted chat model that serves a different queue per specialist.

    ``build_graph`` injects ONE main-tier model for every main node, and the two
    synthesis workers run on separate threads — so a single shared cursor would
    race and interleave the planner's tool calls with the concierge's prose. This
    model instead routes by the domain prompt in the system message ("Trip
    Planner" / "Travel Concierge", else the synthesize node), each queue advancing
    independently under a lock. ``with_structured_output`` serves the supervisor's
    fixed intent.
    """

    intent: Any = None
    _cursors: dict[str, int] = PrivateAttr(
        default_factory=lambda: {"planner": 0, "concierge": 0, "synthesize": 0}
    )
    _lock: Any = PrivateAttr(default_factory=threading.Lock)

    @property
    def _llm_type(self) -> str:
        return "agent-aware-fake"

    @staticmethod
    def _route(messages: list[BaseMessage]) -> str:
        text = " ".join(
            str(getattr(m, "content", ""))
            for m in messages
            if isinstance(m, SystemMessage)
        )
        if "Trip Planner" in text:
            return "planner"
        if "Travel Concierge" in text:
            return "concierge"
        return "synthesize"

    _SCRIPTS = {
        "planner": _PLANNER_SCRIPT,
        "concierge": _CONCIERGE_SCRIPT,
        "synthesize": _SYNTHESIZE_SCRIPT,
    }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        key = self._route(messages)
        script = self._SCRIPTS[key]
        with self._lock:
            i = self._cursors[key]
            self._cursors[key] += 1
        # Clamp so an unexpected extra call (e.g. a reflection revise) repeats the
        # terminal answer instead of raising — the loop still ends deterministically.
        msg = script[min(i, len(script) - 1)]
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        def _call(_messages: Any) -> Any:
            return self.intent

        return RunnableLambda(_call)


_PLAN_EVERYTHING = (
    "Plan everything for a Tokyo weekend: flights, a hotel, places to see, "
    "the weather, local tips and a day-by-day plan"
)


def _stub_weather(monkeypatch) -> None:
    """Remove the one networked planner tool from the loop (deterministic error)."""

    async def _no_network_weather(*args: Any, **kwargs: Any):
        raise CityNotFoundError("weather stubbed offline for the hermetic test")

    monkeypatch.setattr(
        "app.tools.weather_tools.weather_service.get_weather", _no_network_weather
    )


def test_plan_everything_routes_to_one_planner_plus_concierge(agent_db, monkeypatch):
    """A dependent chain yields ONE planner + ONE concierge task and synthesizes,
    completing under ``agent_recursion_limit`` (no GraphRecursionError)."""
    _stub_weather(monkeypatch)

    main = _AgentAwareLLM(
        intent=SupervisorIntent(target_agent="planner", plan=["concierge"])
    )
    graph = build_graph(
        llm=main,
        fast_llm=FakeLLM(responses=["OK"] * 6),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )

    limit = get_settings().agent_recursion_limit
    # Reaching the assertions at all is the recursion-headroom proof: an inner
    # planner loop over budget would raise GraphRecursionError inside the worker.
    out = _drive(
        graph,
        {
            "messages": [HumanMessage(content=_PLAN_EVERYTHING)],
            "user_id": "test-user-1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": "t-plan-everything"}, "recursion_limit": limit},
        context=AgentContext(authenticated=True),
    )

    # Exactly one planner task and one concierge task — the repeated/duplicated
    # planner the old ordered plan would have produced is gone.
    agents = [r["agent"] for r in out.get("task_results", [])]
    assert sorted(agents) == ["concierge", "planner"], agents
    assert agents.count("planner") == 1, "the dependent chain is ONE planner task"

    # A single synthesized answer is present and the graph ended at synthesize.
    assert out["current_flow"] == "synthesize"
    contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert any("Tokyo weekend is planned" in c for c in contents), contents


def test_planner_seven_tool_chain_fits_recursion_budget(agent_db, monkeypatch):
    """MEASURE the planner ReAct loop's super-step count for the 7-tool chain.

    Each ``synthesis_worker`` invokes the planner subgraph with the parent config,
    so the inner loop is bounded by the same ``recursion_limit``. This runs that
    inner planner subgraph directly, counts its super-steps, and asserts the chain
    finishes (a content-bearing final answer) with headroom under the limit.
    """
    _stub_weather(monkeypatch)

    main = _AgentAwareLLM(intent=SupervisorIntent(target_agent="planner"))
    planner = build_planner(lambda hint=None: main)

    limit = get_settings().agent_recursion_limit
    # ``updates`` yields one chunk per node execution, i.e. one per pregel
    # super-step — exactly what ``recursion_limit`` counts against.
    steps = 0
    final: AIMessage | None = None
    for chunk in planner.stream(
        {
            "messages": [HumanMessage(content=_PLAN_EVERYTHING)],
            "user_id": "test-user-1",
            "trip_id": None,
        },
        {"recursion_limit": limit},
        stream_mode="updates",
        context=AgentContext(authenticated=True),
    ):
        steps += 1
        node_update = chunk.get("assistant")
        if node_update and node_update.get("messages"):
            final = node_update["messages"][-1]

    # The whole 7-tool chain ran and ended on a prose answer (not mid-loop).
    assert isinstance(final, AIMessage) and not getattr(final, "tool_calls", None)
    assert "day by day" in str(final.content)

    # Fits under the configured budget with headroom — the whole point of routing
    # a dependent chain to ONE specialist instead of raising the limit.
    assert steps < limit, f"planner chain streamed {steps} states; limit is {limit}"
