"""SC-6: filesystem permissions deny writes outside the dossier / plan / memory routes.

A scripted write to ``/skills/x/SKILL.md`` is denied and persists nothing; a write to
``/research/flights.md`` succeeds and lands in the store under the run's namespace.

Note: ``CompositeBackend`` strips the ``/research/`` route prefix before delegating, so the
persisted store key is ``/flights.md`` (not ``/research/flights.md``).
"""

from __future__ import annotations

from app.clients.llm import FakeLLM
from langchain_core.messages import ToolMessage

from tests.research.conftest import RESEARCH_NS, THREAD_CONFIG, build, context


def _tool_messages(result) -> list[ToolMessage]:
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


def test_write_denied_outside_allowed_routes(store) -> None:
    model = FakeLLM(
        responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/skills/x/SKILL.md",
                            "content": "hijack",
                        },
                        "id": "deny",
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/research/flights.md",
                            "content": "Da Nang → Bangkok (search_flights)",
                        },
                        "id": "allow",
                    }
                ],
            },
            {"content": "done"},
        ]
    )
    agent = build(store, llm=model)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "write files"}]},
        THREAD_CONFIG,
        context=context(),
    )

    messages = _tool_messages(result)
    denied = next(m for m in messages if m.tool_call_id == "deny")
    assert "permission denied" in denied.content
    assert "/skills/x/SKILL.md" in denied.content

    # The denied write persisted nothing anywhere.
    assert store.get(RESEARCH_NS, "/x/SKILL.md") is None
    assert [i.key for i in store.search(("users", "u1", "research", "t1"))] == [
        "/flights.md"
    ]

    allowed = next(m for m in messages if m.tool_call_id == "allow")
    assert "permission denied" not in allowed.content
    item = store.get(RESEARCH_NS, "/flights.md")
    assert item is not None
    assert "search_flights" in item.value["content"]
