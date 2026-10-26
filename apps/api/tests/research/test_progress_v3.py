"""derive_events understands LangGraph v3 protocol events (#270)."""

from app.streaming.research_events import (
    ResearchFile,
    ResearchPhase,
    ResearchTool,
    derive_events,
)


def _v3(method: str, data, namespace=()):
    return {
        "type": "event",
        "method": method,
        "params": {"namespace": list(namespace), "timestamp": 0, "data": data},
    }


def test_v3_tool_started_and_finished_map_to_tool_events() -> None:
    started = derive_events(
        _v3(
            "tools",
            {
                "event": "tool-started",
                "tool_call_id": "c1",
                "tool_name": "write_file",
                "input": {"file_path": "/research/a.md", "content": "SECRET"},
            },
        )
    )
    assert [type(e) for e in started] == [ResearchTool, ResearchFile]
    assert started[0].status == "start"
    assert started[1].path == "/research/a.md"
    for e in started:
        assert "SECRET" not in e.to_sse().data

    finished = derive_events(
        _v3("tools", {"event": "tool-finished", "tool_call_id": "c1", "output": "ok"})
    )
    assert len(finished) == 1 and isinstance(finished[0], ResearchTool)
    assert finished[0].name == "write_file" and finished[0].status == "end"


def test_v3_values_todos_map_to_phase_event() -> None:
    events = derive_events(
        _v3("values", {"todos": [{"content": "flights", "status": "in_progress"}]})
    )
    assert len(events) == 1 and isinstance(events[0], ResearchPhase)
    assert events[0].todos[0]["content"] == "flights"


def test_v3_unrelated_methods_map_to_empty() -> None:
    assert derive_events(_v3("messages", ["x", {}])) == []
    assert derive_events(_v3("values", {"messages": []})) == []
