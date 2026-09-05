"""End-to-end acceptance for MIN-57 language-aware panel localization.

Offline, network-free acceptance over the full stream path: a fake graph drives
``stream_agent_events`` (reusing the ``test_mapper_language`` fake-graph shape and
event-collection helper), and a node-level supervisor assertion proves the
empty-code stickiness fallback that the mapper unit test could not reach.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.agents.supervisor import SupervisorIntent, make_supervisor
from app.streaming.mapper import stream_agent_events
from app.streaming.panels.places import CATEGORY_VI
from langchain_core.messages import HumanMessage, ToolMessage


class _FakeGraph:
    """Replays scripted (ns, mode, data) tuples through ``astream`` with a
    persisted-state ``aget_state`` seed — mirrors
    ``tests/streaming/test_mapper_language._FakeGraph``."""

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


def _places_tool_msg() -> ToolMessage:
    return ToolMessage(
        content="",
        tool_call_id="t1",
        status="success",
        artifact={
            "kind": "places",
            "data": {"places": [{"description": "A cozy cafe.", "category": "cafe"}]},
        },
    )


def test_e2e_vi_full_path_localizes_and_tags_language():
    # Supervisor persists language=vi + concierge flow, then the sub-agent emits a
    # places panel. Bounded category swaps via the vi table; the free-form place
    # description passes through (search_places localized it at tool time).
    items = [
        (
            (),
            "updates",
            {"supervisor": {"language": "vi", "current_flow": "concierge"}},
        ),
        (("concierge:1",), "updates", {"tools": {"messages": [_places_tool_msg()]}}),
    ]
    graph = _FakeGraph(
        items,
        values={"language": "vi", "current_flow": "concierge"},
    )
    out = _run(graph)

    panels = [d for n, d in out if n == "panel"]
    assert len(panels) == 1
    panel = panels[0]
    place = panel["data"]["places"][0]
    assert place["description"] == "A cozy cafe."  # prose untouched here
    assert place["category"] == CATEGORY_VI["cafe"]  # bounded lookup
    assert panel["language"] == "vi"

    done = next(d for n, d in out if n == "done")
    assert done["language"] == "vi"


def test_e2e_en_path_is_byte_identical_and_tags_en():
    # No language delta and no persisted language → default en. The panel data
    # must be byte-identical to the input artifact data (strict identity no-op).
    input_data = {"places": [{"description": "A cozy cafe.", "category": "cafe"}]}
    items = [
        (("concierge:1",), "updates", {"tools": {"messages": [_places_tool_msg()]}}),
    ]
    graph = _FakeGraph(
        items,
        values={"current_flow": "concierge"},
    )
    out = _run(graph)

    panels = [d for n, d in out if n == "panel"]
    assert len(panels) == 1
    panel = panels[0]
    assert panel["data"] == input_data  # unchanged, English preserved
    assert panel["language"] == "en"

    done = next(d for n, d in out if n == "done")
    assert done["language"] == "en"


def test_e2e_established_vi_sticks_on_empty_code_turn():
    # A short "ok" turn where the router returns no confident language code. The
    # supervisor node must retain the established vi (empty-code fallback) — the
    # stickiness the mapper unit test cannot exercise on its own.
    class _RouterLLM:
        def __init__(self, intent):
            self._intent = intent

        def with_structured_output(self, *_a, **_k):
            return self

        def invoke(self, _messages):
            return self._intent

    llm = _RouterLLM(SupervisorIntent(target_agent="concierge", language=""))
    node = make_supervisor(llm)
    cmd = node({"messages": [HumanMessage("ok")], "language": "vi"}, None)
    assert cmd.update["language"] == "vi"
