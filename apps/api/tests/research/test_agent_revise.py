"""SC-8: a second turn on the same thread reuses the checkpoint and edits rather than rewrites.

Turn one writes ``/research/overview.md``; turn two, on the same thread id, changes it with
``edit_file`` (not ``write_file``). ``aget_state`` then shows two ``HumanMessage`` turns and
the edited content.
"""

from __future__ import annotations

import asyncio

from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage, ToolMessage

from tests.research.conftest import RESEARCH_NS, THREAD_CONFIG, build, context


def test_second_turn_resumes_thread_and_edits(store) -> None:
    model = FakeLLM(
        responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/research/overview.md",
                            "content": "Overview v1 (get_trip_summary)",
                        },
                        "id": "w1",
                    }
                ],
            },
            {"content": "first pass done"},
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "edit_file",
                        "args": {
                            "file_path": "/research/overview.md",
                            "old_string": "v1",
                            "new_string": "v2",
                        },
                        "id": "e1",
                    }
                ],
            },
            {"content": "revision done"},
        ]
    )
    agent = build(store, llm=model)

    agent.invoke(
        {"messages": [{"role": "user", "content": "research my trip"}]},
        THREAD_CONFIG,
        context=context(),
    )
    second = agent.invoke(
        {"messages": [{"role": "user", "content": "tighten the overview"}]},
        THREAD_CONFIG,
        context=context(),
    )

    # The revise turn ran edit_file (an edit tool message with the file's path exists).
    edits = [
        m
        for m in second["messages"]
        if isinstance(m, ToolMessage) and m.name == "edit_file"
    ]
    assert edits and any("/research/overview.md" in m.content for m in edits)

    snapshot = asyncio.run(agent.aget_state(THREAD_CONFIG))
    humans = [m for m in snapshot.values["messages"] if isinstance(m, HumanMessage)]
    assert len(humans) == 2

    # In-place edit, not a rewrite: only "v1" -> "v2" changed; surrounding text is intact.
    item = store.get(RESEARCH_NS, "/overview.md")
    assert item is not None
    assert item.value["content"] == "Overview v2 (get_trip_summary)"
