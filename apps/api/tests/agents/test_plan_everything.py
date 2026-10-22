"""A dependent chain routes to ONE planner specialist that runs the whole tool chain in its own ReAct loop.

Proves topology (plan=["concierge"] yields one planner + one concierge task and a
single synthesized answer) and that the planner's 7-tool loop fits under
agent_recursion_limit with headroom. The two parallel synthesis workers share the
injected main model on separate threads, so _AgentAwareLLM routes scripted
responses per specialist by system prompt to keep each script race-free.
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
    """Run the graph asynchronously; synthesis_worker is an async node that a sync invoke cannot execute."""
    return asyncio.run(graph.ainvoke(*args, **kwargs))


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Fresh seeded temp SQLite DB so in-graph planner tools resolve a session from the setting."""
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


# Planner chain: flights, hotel, places, weather, create trip, two itinerary items, then prose.
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
    """Scripted chat model serving a per-specialist queue, routed by the domain prompt in the system message, since the synthesis workers share one injected model across threads."""

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
        # Clamp so an unexpected extra call repeats the terminal answer instead of raising.
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
    # Reaching the assertions is the headroom proof: an over-budget inner planner loop would raise GraphRecursionError.
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

    # Exactly one planner task and one concierge task, no duplicate planner.
    agents = [r["agent"] for r in out.get("task_results", [])]
    assert sorted(agents) == ["concierge", "planner"], agents
    assert agents.count("planner") == 1, "the dependent chain is ONE planner task"

    # A single synthesized answer is present and the graph ended at synthesize.
    assert out["current_flow"] == "synthesize"
    contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert any("Tokyo weekend is planned" in c for c in contents), contents


def test_planner_seven_tool_chain_fits_recursion_budget(agent_db, monkeypatch):
    """Measure the planner ReAct loop's super-step count for the 7-tool chain; the inner subgraph inherits recursion_limit, so it must finish with headroom."""
    _stub_weather(monkeypatch)

    main = _AgentAwareLLM(intent=SupervisorIntent(target_agent="planner"))
    planner = build_planner(lambda hint=None: main)

    limit = get_settings().agent_recursion_limit
    # ``updates`` yields one chunk per super-step, exactly what recursion_limit counts against.
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

    # Fits under the budget with headroom.
    assert steps < limit, f"planner chain streamed {steps} states; limit is {limit}"
