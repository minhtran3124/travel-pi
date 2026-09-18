"""SC-5: the research agent compiles offline and exposes the right tool surface.

The model-facing tools must include the deep-agent staples and the delegation tool, exclude
``execute``, and no ``general-purpose`` subagent may be auto-registered.
"""

from __future__ import annotations

from tests.research.conftest import RecordingFakeLLM, build, context

_EXPECTED = {"task", "write_todos", "read_file", "write_file", "edit_file"}


def _task_description(agent) -> str:
    return agent.nodes["tools"].bound.tools_by_name["task"].description


def test_compiles_and_binds_expected_tools(store) -> None:
    model = RecordingFakeLLM(responses=[{"content": "done"}])
    agent = build(store, llm=model)

    # One no-op turn (no rubric) so the model binds its tools exactly once.
    agent.invoke(
        {"messages": [{"role": "user", "content": "research my trip"}]},
        THREAD := {"configurable": {"thread_id": "research:u1:t1"}},
        context=context(),
    )
    assert THREAD  # thread config used

    bound = set(RecordingFakeLLM._bound)
    assert bound >= _EXPECTED, f"missing {_EXPECTED - bound}"
    assert "execute" not in bound


def test_no_general_purpose_subagent(store) -> None:
    model = RecordingFakeLLM(responses=[{"content": "done"}])
    agent = build(store, llm=model)

    description = _task_description(agent)
    # The listing has one "- <name>: ..." line per registered subagent; no general-purpose.
    assert "- general-purpose:" not in description
    for dimension in ("flights", "stays", "days", "entry_season", "budget"):
        assert f"- {dimension}:" in description
