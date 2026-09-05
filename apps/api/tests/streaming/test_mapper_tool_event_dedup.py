"""Tool events are emitted once per call, and never replayed from thread history.

A sub-agent shares the parent's state schema, so ``astream(subgraphs=True)``
surfaces its ``ToolMessage`` twice per turn (subgraph ``tools`` node + parent
sub-agent node) and the parent-level delta carries the thread's WHOLE
``messages`` list — prior turns' tool calls/results included. Each replay used
to become a fresh ``tool_call`` activity step, a ``panel`` and a ``tool_result``.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.streaming.mapper import stream_agent_events
from langchain_core.messages import AIMessage, ToolMessage


class _FakeGraph:
    def __init__(self, items, *, values=None):
        self._items = items
        self._values = values or {}

    async def astream(self, stream_input, cfg, *, stream_mode, subgraphs, context=None):
        for item in self._items:
            yield item

    async def aget_state(self, cfg):
        return SimpleNamespace(interrupts=(), values=self._values)


def _run(graph):
    async def collect():
        out = []
        async for ev in stream_agent_events(
            graph, {"messages": []}, cfg={}, conversation_id="c1"
        ):
            out.append((ev.event, json.loads(ev.data)))
        return out

    return asyncio.run(collect())


def _call(i: str) -> AIMessage:
    return AIMessage(
        id=f"ai-{i}",
        content="",
        tool_calls=[{"name": "search_places", "args": {"city": "Da Nang"}, "id": i}],
    )


def _result(i: str) -> ToolMessage:
    return ToolMessage(
        id=f"tool-{i}",
        content="4 places",
        tool_call_id=i,
        status="success",
        artifact={
            "kind": "places",
            "data": {
                "places": [
                    {"description": f"desc {n}", "category": "cafe"} for n in range(4)
                ]
            },
        },
    )


def _counts(out):
    kinds = [e for e, _ in out]
    return {k: kinds.count(k) for k in ("tool_call", "panel", "tool_result")}


def test_same_turn_double_sighting_emits_each_tool_event_once():
    call, result = _call("c1"), _result("c1")
    items = [
        (("concierge:1",), "updates", {"assistant": {"messages": [call]}}),
        (("concierge:1",), "updates", {"tools": {"messages": [result]}}),
        # Parent-level update for the sub-agent node: the subgraph's whole output.
        ((), "updates", {"concierge": {"messages": [call, result]}}),
    ]
    out = _run(_FakeGraph(items))

    assert _counts(out) == {"tool_call": 1, "panel": 1, "tool_result": 1}


def test_thread_history_is_not_replayed_as_new_tool_events():
    old_call, old_result = _call("c-old"), _result("c-old")
    new_call, new_result = _call("c-new"), _result("c-new")
    items = [
        (("concierge:1",), "updates", {"assistant": {"messages": [new_call]}}),
        (("concierge:1",), "updates", {"tools": {"messages": [new_result]}}),
        (
            (),
            "updates",
            {"concierge": {"messages": [old_call, old_result, new_call, new_result]}},
        ),
    ]
    graph = _FakeGraph(
        items, values={"messages": [old_call, old_result], "language": "vi"}
    )
    out = _run(graph)

    assert _counts(out) == {"tool_call": 1, "panel": 1, "tool_result": 1}
    assert [d["id"] for e, d in out if e == "tool_call"] == ["c-new"]
    assert [d["tool_call_id"] for e, d in out if e == "panel"] == ["c-new"]


def test_history_message_without_id_is_still_deduped_by_tool_call_id():
    # Messages persisted before ids were assigned: fall back to the call id.
    old_call = AIMessage(
        content="", tool_calls=[{"name": "search_places", "args": {}, "id": "c-old"}]
    )
    old_result = ToolMessage(content="x", tool_call_id="c-old", status="success")
    items = [((), "updates", {"concierge": {"messages": [old_call, old_result]}})]
    out = _run(_FakeGraph(items, values={"messages": [old_call, old_result]}))

    assert _counts(out) == {"tool_call": 0, "panel": 0, "tool_result": 0}
