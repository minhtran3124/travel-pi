"""Mapper language tagging + panel localization (MIN-57 Task 3.1).

The stream mapper captures the conversation language from the supervisor's
``updates`` delta and, for the rest of the turn, tags every ``panel``/``done``
event with it and runs panel payloads through ``localize_panel``. ``en`` is a
strict identity no-op; ``vi`` swaps the bounded panel strings.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.streaming.mapper import stream_agent_events
from app.streaming.panels.places import CATEGORY_VI
from app.streaming.panels.weather import WEATHER_VI
from langchain_core.messages import ToolMessage


class _FakeGraph:
    """Replays scripted (ns, mode, data) tuples through ``astream``.

    Mirrors ``tests/api/agent/test_stream_events._FakeGraph`` but adds the
    ``translate_llm`` handle the mapper reads for the panel-prose translator.
    """

    def __init__(self, items, *, values=None, translate_llm=None):
        self._items = items
        self._values = values or {}
        self.translate_llm = translate_llm

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


def _weather_tool_msg() -> ToolMessage:
    return ToolMessage(
        content="",
        tool_call_id="t1",
        status="success",
        artifact={
            "kind": "weather",
            "data": {"current": {"description": "Clear sky"}, "daily": []},
        },
    )


def _places_tool_msg() -> ToolMessage:
    return ToolMessage(
        content="",
        tool_call_id="t2",
        status="success",
        artifact={
            "kind": "places",
            "data": {"places": [{"description": "A cozy cafe.", "category": "cafe"}]},
        },
    )


class _FakeTranslateLLM:
    """Async stand-in for ``graph.translate_llm`` — echoes a ``VI:``-prefixed
    translation of the last (human) message, exercising the ``ainvoke`` path."""

    def __init__(self):
        self.calls: list[str] = []

    async def ainvoke(self, messages):
        text = messages[-1].content
        self.calls.append(text)
        return SimpleNamespace(content="VI:" + text)


def test_mapper_localizes_and_tags_panel_and_done_vi():
    # Supervisor persists language=vi (top-level namespace), then a concierge
    # sub-agent emits a weather panel tool result.
    items = [
        ((), "updates", {"supervisor": {"language": "vi"}}),
        (("concierge:1",), "updates", {"tools": {"messages": [_weather_tool_msg()]}}),
    ]
    graph = _FakeGraph(items, values={"current_flow": "concierge"}, translate_llm=None)
    out = _run(graph)

    panels = [d for n, d in out if n == "panel"]
    assert len(panels) == 1
    panel = panels[0]
    assert panel["language"] == "vi"
    assert panel["data"]["current"]["description"] == WEATHER_VI["Clear sky"]

    done = next(d for n, d in out if n == "done")
    assert done["language"] == "vi"


def test_mapper_en_path_is_identity_and_tags_en():
    # No language delta anywhere → default en. Panel data must be byte-identical
    # to the input artifact data, and both panel/done tag language=en.
    input_data = {"current": {"description": "Clear sky"}, "daily": []}
    items = [
        (("concierge:1",), "updates", {"tools": {"messages": [_weather_tool_msg()]}}),
    ]
    graph = _FakeGraph(items, values={"current_flow": "concierge"}, translate_llm=None)
    out = _run(graph)

    panels = [d for n, d in out if n == "panel"]
    assert len(panels) == 1
    panel = panels[0]
    assert panel["language"] == "en"
    assert panel["data"] == input_data  # unchanged, English preserved

    done = next(d for n, d in out if n == "done")
    assert done["language"] == "en"


def test_mapper_translates_place_prose_via_async_llm():
    # Supervisor persists language=vi, then a concierge sub-agent emits a places
    # panel whose free-form description flows through the async translate_llm.
    tl = _FakeTranslateLLM()
    items = [
        ((), "updates", {"supervisor": {"language": "vi"}}),
        (("concierge:1",), "updates", {"tools": {"messages": [_places_tool_msg()]}}),
    ]
    graph = _FakeGraph(items, values={"current_flow": "concierge"}, translate_llm=tl)
    out = _run(graph)

    panels = [d for n, d in out if n == "panel"]
    assert len(panels) == 1
    panel = panels[0]
    assert panel["language"] == "vi"
    place = panel["data"]["places"][0]
    # Prose translated through the async LLM; bounded category via the vi table.
    assert place["description"] == "VI:A cozy cafe."
    assert place["category"] == CATEGORY_VI["cafe"]
    assert tl.calls == ["A cozy cafe."]


def test_mapper_seeds_language_from_state_on_hitl_resume():
    # A HITL-resume turn skips the supervisor, so astream emits NO language delta
    # (only a sub-agent weather panel). The pre-loop aget_state seed must still
    # tag/localize the panel as vi from the persisted state values.
    items = [
        (("concierge:1",), "updates", {"tools": {"messages": [_weather_tool_msg()]}}),
    ]
    graph = _FakeGraph(
        items,
        values={"language": "vi", "current_flow": "concierge"},
        translate_llm=None,
    )
    out = _run(graph)

    panels = [d for n, d in out if n == "panel"]
    assert len(panels) == 1
    panel = panels[0]
    assert panel["language"] == "vi"
    assert panel["data"]["current"]["description"] == WEATHER_VI["Clear sky"]

    done = next(d for n, d in out if n == "done")
    assert done["language"] == "vi"
