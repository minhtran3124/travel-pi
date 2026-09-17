"""A fanned-out worker must execute tools exactly like a single-specialist turn.

These tests assert on what the tools actually RETURNED, so a tools-node crash
surfaces instead of hiding behind topology-only assertions.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from app.agents.graph import build_graph
from app.agents.retry import GRACEFUL_MSG, INTERNAL_FAULT_MSG
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
    """Stub the service, not the async ``@tool`` wrapper — the wrapper's async-ness is under test."""

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
    """Scripted per-specialist model that clamps to the last response and records the concierge's inbound messages."""

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


# Either message means the tools node died before the tool ran.
_NODE_DIED = (GRACEFUL_MSG, INTERNAL_FAULT_MSG)


def _by_name(messages: list[ToolMessage], name: str) -> ToolMessage:
    match = [m for m in messages if m.name == name]
    assert match, f"no ToolMessage for {name}; got {[m.name for m in messages]}"
    return match[0]


def test_async_tool_succeeds_in_a_fanned_out_worker(agent_db, offline_weather):
    """The async-only tool must reach its own body, not the tools-node fallback."""
    weather = _by_name(_fan_out_and_capture_tool_messages(), ASYNC_TOOL)

    assert not any(m in str(weather.content) for m in _NODE_DIED), (
        "the tools node died instead of running the async tool — the worker is "
        "invoking the sub-agent synchronously again (#178)"
    )
    assert "weather stubbed offline" in str(weather.content)


def test_sibling_sync_tool_is_not_collateral_damaged(agent_db, offline_weather):
    """A healthy sync tool batched with an async one must still return its data."""
    tips = _by_name(_fan_out_and_capture_tool_messages(), SYNC_TOOL)

    assert not any(m in str(tips.content) for m in _NODE_DIED), (
        "a healthy synchronous tool was reported as failed because a sibling "
        "async call killed the tools node (#178)"
    )
    assert tips.status != "error", f"{SYNC_TOOL} returned an error: {tips.content}"
    content = str(tips.content)
    assert '"count":' in content and '"count": 0' not in content
