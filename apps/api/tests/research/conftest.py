"""Shared fixtures for the trip-research deep-agent tests.

Everything runs offline: ``FakeLLM`` for the agent and grader, ``InMemoryStore`` for the
dossier / memory routes, and ``MemorySaver`` for thread resume. No network, no real LLM.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.clients.llm import FakeLLM
from app.prompts.registry import registry
from app.research.agent import build_research_agent
from app.research.context import ResearchContext
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore

USER_ID = "u1"
TRIP_ID = "t1"
RESEARCH_NS = ("users", USER_ID, "research", TRIP_ID)
MEMORY_NS = ("users", USER_ID, "research_memory")
THREAD_CONFIG = {"configurable": {"thread_id": f"research:{USER_ID}:{TRIP_ID}"}}


class RecordingFakeLLM(FakeLLM):
    """`FakeLLM` that records the tool names bound to it, for tool-exposure assertions."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakeLLM:
        type(self)._bound = [getattr(t, "name", str(t)) for t in tools]
        return self


def context() -> ResearchContext:
    """The per-run context every invoke passes as ``context=``."""
    return ResearchContext(
        user_id=USER_ID,
        trip_id=TRIP_ID,
        run_id="r1",
        language="en",
        timezone="UTC",
    )


def rubric() -> str:
    """The grader rubric text the runner supplies via ``state['rubric']``."""
    return registry.get("trip_research_grader")


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def build(
    store: InMemoryStore,
    *,
    llm: FakeLLM,
    grader: FakeLLM | None = None,
) -> CompiledStateGraph:
    """Build the research agent on *store* with scripted models and a fresh checkpointer."""
    return build_research_agent(
        store=store,
        checkpointer=MemorySaver(),
        llm=llm,
        grader_llm=grader or FakeLLM(responses=[{"content": "ok"}]),
    )
