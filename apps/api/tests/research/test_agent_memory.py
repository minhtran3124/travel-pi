"""SC-30: the guarded ``/memory/`` route rejects an injection write and accepts a plain line.

The write path runs through the built agent's ``write_file`` tool → ``CompositeBackend`` →
``GuardedStoreBackend``, so this exercises the wiring, not just the backend in isolation. The
injection phrase is reused from Task 1.5's memory unit test so it stays grounded in the guard.
"""

from __future__ import annotations

from app.clients.llm import FakeLLM
from langchain_core.messages import ToolMessage

from tests.research.conftest import MEMORY_NS, THREAD_CONFIG, build, context
from tests.research.test_memory_unit import _INJECTION


def _write_call(file_path: str, content: str, call_id: str) -> dict:
    return {
        "content": "",
        "tool_calls": [
            {
                "name": "write_file",
                "args": {"file_path": file_path, "content": content},
                "id": call_id,
            }
        ],
    }


def test_memory_route_rejects_injection_accepts_plain_line(store) -> None:
    model = FakeLLM(
        responses=[
            _write_call("/memory/AGENTS.md", _INJECTION, "inject"),
            _write_call("/memory/AGENTS.md", "- diet: vegetarian", "plain"),
            {"content": "done"},
        ]
    )
    agent = build(store, llm=model)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "remember this"}]},
        THREAD_CONFIG,
        context=context(),
    )
    messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]

    rejected = next(m for m in messages if m.tool_call_id == "inject")
    assert "permission denied" in rejected.content
    assert "blocked_pattern" in rejected.content
    # Nothing persisted from the injection attempt.
    assert store.get(MEMORY_NS, "/AGENTS.md") is None or (
        _INJECTION not in store.get(MEMORY_NS, "/AGENTS.md").value["content"]
    )

    accepted = next(m for m in messages if m.tool_call_id == "plain")
    assert "permission denied" not in accepted.content
    item = store.get(MEMORY_NS, "/AGENTS.md")
    assert item is not None
    assert "- diet: vegetarian" in item.value["content"]
