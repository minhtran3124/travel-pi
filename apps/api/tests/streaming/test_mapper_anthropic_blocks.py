"""Claude streams list-of-blocks content; only the text deltas may reach the wire (#254)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.streaming.mapper import stream_agent_events
from langchain_core.messages import AIMessageChunk


class _FakeGraph:
    def __init__(self, items):
        self._items = items

    async def astream(self, stream_input, cfg, *, stream_mode, subgraphs, context=None):
        for item in self._items:
            yield item

    async def aget_state(self, cfg):
        return SimpleNamespace(interrupts=(), values={})


def _run(items) -> list[tuple[str, dict]]:
    async def collect():
        out = []
        async for ev in stream_agent_events(
            _FakeGraph(items), {"messages": []}, cfg={}, conversation_id="c1"
        ):
            out.append((ev.event, json.loads(ev.data)))
        return out

    return asyncio.run(collect())


def _synth(chunk: AIMessageChunk):
    return ((), "messages", (chunk, {"langgraph_node": "synthesize"}))


def _tokens(out):
    return [d["content"] for n, d in out if n == "token"]


def test_only_text_block_is_emitted_as_token():
    text = AIMessageChunk(
        id="synth-1", content=[{"type": "text", "text": "Hi", "index": 0}]
    )
    thinking = AIMessageChunk(
        id="synth-1", content=[{"type": "thinking", "thinking": "hmm...", "index": 0}]
    )
    out = _run([_synth(thinking), _synth(text)])
    assert _tokens(out) == ["Hi"]


def test_tool_use_and_input_json_delta_chunks_emit_nothing():
    tool_use = AIMessageChunk(
        id="synth-1",
        content=[
            {"type": "tool_use", "id": "t1", "name": "x", "input": {}, "index": 1}
        ],
    )
    delta = AIMessageChunk(
        id="synth-1",
        content=[{"type": "input_json_delta", "partial_json": '{"a"', "index": 1}],
    )
    assert _tokens(_run([_synth(tool_use), _synth(delta)])) == []
