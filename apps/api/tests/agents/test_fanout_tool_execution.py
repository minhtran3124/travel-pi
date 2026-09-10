"""A fanned-out worker must execute tools exactly like a single-specialist turn (#178).

`synthesis_worker` used to run each specialist with a **sync** ``subagent.invoke``.
Six agent tools are ``async def`` — ``get_weather``, ``get_packing``,
``get_air_quality``, ``get_climate``, ``get_route``, ``get_city_route`` — and both
the planner and the concierge bind all of them. Under a sync invocation one such
call raises ``NotImplementedError: StructuredTool does not support sync
invocation``, which kills the whole ``tools`` node; ``TOOL_FAULT``'s
``graceful_fallback`` then hands the model ``GRACEFUL_MSG`` for **every** pending
call in that batch — including healthy synchronous ones. The specialist duly told
the traveller the data was temporarily unavailable, which was false and identical
on retry.

These tests assert on what the tools actually RETURNED. That is the point: the
pre-existing fan-out test (``test_plan_everything.py``) asserts topology and the
recursion budget only, so it passed for months while the tools node crashed
underneath it.

Hermetic: the seeded temp SQLite DB backs the real tools, and the ONE networked
tool has its *service* stubbed — never its wrapper, since replacing an async
wrapper with a sync stub would recreate exactly the blind spot under test.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from app.agents.graph import build_graph
from app.agents.retry import GRACEFUL_MSG
from app.agents.supervisor import SupervisorIntent
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.exceptions import CityNotFoundError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import PrivateAttr

SYNC_TOOL = "get_local_tips"
ASYNC_TOOL = "get_weather"


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """A seeded temp SQLite DB so the real tools run offline."""
    url = f"sqlite:///{tmp_path / 'fanout.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


@pytest.fixture
def offline_weather(monkeypatch):
    """Remove the network under ``get_weather`` while keeping the tool async.

    Stubbing the *service* rather than the ``@tool`` wrapper is deliberate: the
    wrapper's async-ness is the property under test, so replacing it with a sync
    callable would make these tests pass against the very bug they exist to catch.
    """

    async def _no_network(*args: Any, **kwargs: Any):
        raise CityNotFoundError("weather stubbed offline for the hermetic test")

    monkeypatch.setattr(
        "app.tools.weather_tools.weather_service.get_weather", _no_network
    )


_BOTH_TOOLS = AIMessage(
    content="",
    tool_calls=[
        {"name": SYNC_TOOL, "args": {"city": "Da Nang"}, "id": "tips-1"},
        {"name": ASYNC_TOOL, "args": {"city": "Da Nang"}, "id": "wx-1"},
    ],
)

_SCRIPTS: dict[str, list[AIMessage]] = {
    # The planner is not the subject here; one content-bearing answer ends its loop.
    "planner": [AIMessage(content="Planner done.")],
    "concierge": [_BOTH_TOOLS, AIMessage(content="Concierge done.")],
    "synthesize": [AIMessage(content="Combined answer.")],
}


class _RecordingLLM(BaseChatModel):
    """Per-specialist scripted model that also records what the concierge saw.

    Two properties matter here and neither is available from ``FakeLLM``:

    * it **clamps** to the last scripted response instead of cycling, so an extra
      round ends the ReAct loop rather than replaying the tool call forever; and
    * it captures the concierge's inbound messages, which is the only way to see
      the ``ToolMessage``s — ``synthesis_worker`` deliberately does not propagate
      the inner sub-agent's messages to the parent state.
    """

    intent: Any = None
    seen: Any = None
    _cursors: dict[str, int] = PrivateAttr(
        default_factory=lambda: {"planner": 0, "concierge": 0, "synthesize": 0}
    )
    _lock: Any = PrivateAttr(default_factory=threading.Lock)

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

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

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        key = self._route(messages)
        if key == "concierge" and self.seen is not None:
            with self._lock:
                self.seen.extend(m for m in messages if isinstance(m, ToolMessage))
        script = _SCRIPTS[key]
        with self._lock:
            i = self._cursors[key]
            self._cursors[key] += 1
        return ChatResult(
            generations=[ChatGeneration(message=script[min(i, len(script) - 1)])]
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        return RunnableLambda(lambda _m: self.intent)


def _fan_out_and_capture_tool_messages() -> list[ToolMessage]:
    """Run one fanned-out turn through the real graph and return the ToolMessages
    the concierge worker's inner sub-agent actually received."""
    seen: list[ToolMessage] = []
    llm = _RecordingLLM(
        intent=SupervisorIntent(
            target_agent="planner", plan=["concierge"], language="en"
        ),
        seen=seen,
    )
    graph = build_graph(
        llm=llm, fast_llm=llm, checkpointer=MemorySaver(), store=InMemoryStore()
    )
    asyncio.run(
        graph.ainvoke(
            {
                "messages": [HumanMessage(content="Da Nang tips and the weather")],
                "user_id": "u1",
                "trip_id": None,
            },
            {"configurable": {"thread_id": "gh178-fanout"}, "recursion_limit": 25},
        )
    )
    return seen


def _by_name(messages: list[ToolMessage], name: str) -> ToolMessage:
    match = [m for m in messages if m.name == name]
    assert match, f"no ToolMessage for {name}; got {[m.name for m in messages]}"
    return match[0]


def test_async_tool_succeeds_in_a_fanned_out_worker(agent_db, offline_weather):
    """The async-only tool must reach its own body, not the tools-node fallback.

    With the service stubbed, its honest outcome is a domain error naming the
    stub. What must never appear is ``GRACEFUL_MSG`` — that means the node died
    before the tool ran, which is #178.
    """
    weather = _by_name(_fan_out_and_capture_tool_messages(), ASYNC_TOOL)

    assert GRACEFUL_MSG not in str(weather.content), (
        "the tools node died instead of running the async tool — the worker is "
        "invoking the sub-agent synchronously again (#178)"
    )
    assert "weather stubbed offline" in str(weather.content)


def test_sibling_sync_tool_is_not_collateral_damaged(agent_db, offline_weather):
    """A healthy sync tool batched with an async one must still return its data.

    This is the half that made #178 user-visible: ``get_local_tips`` cannot fail
    on its own, yet it was reported to the model as an outage because a sibling
    call in the same batch took the node down.
    """
    tips = _by_name(_fan_out_and_capture_tool_messages(), SYNC_TOOL)

    assert GRACEFUL_MSG not in str(tips.content), (
        "a healthy synchronous tool was reported as an outage because a sibling "
        "async call killed the tools node (#178)"
    )
    assert tips.status != "error", f"{SYNC_TOOL} returned an error: {tips.content}"
    content = str(tips.content)
    assert '"count":' in content and '"count": 0' not in content
