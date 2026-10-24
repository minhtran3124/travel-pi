"""Claude list-content blocks must read as plain text everywhere an answer is consumed (#254)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents.subagents.synthesis_worker import (
    _AGENT_BUILDERS,
    _last_assistant_content,
    build_synthesis_worker,
)
from langchain_core.messages import HumanMessage
from tests.fixtures.anthropic_llm import AnthropicShapedFakeLLM, anthropic_message


def test_last_assistant_content_reads_text_not_block_list():
    assert _last_assistant_content([anthropic_message("Hello")]) == "Hello"


def test_thinking_only_message_is_skipped():
    thinking_only = anthropic_message("")
    assert (
        _last_assistant_content([anthropic_message("Hello"), thinking_only]) == "Hello"
    )


def test_synthesis_worker_findings_are_text(monkeypatch):
    llm = AnthropicShapedFakeLLM(responses=["Hello"])

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            return {**state, "messages": [llm.invoke("hi")]}

    monkeypatch.setitem(_AGENT_BUILDERS, "planner", lambda _r: FakeGraph())
    worker = build_synthesis_worker(lambda _n, _h=None: None)
    state = {
        "messages": [HumanMessage(content="plan and check weather")],
        "task": {"agent": "planner", "index": 0},
        "trip_id": None,
        "awaiting_user": False,
    }
    cmd = asyncio.run(worker(state, SimpleNamespace(config=None)))
    assert cmd.update["task_results"][0]["findings"] == "Hello"
