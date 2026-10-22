"""The research launcher's code-authored reply reaches the chat stream.

The ``research`` node is a top-level, LLM-free node: its ``AIMessage`` never
arrives as a ``messages``-mode chunk, only in the ``updates`` delta. Without a
``token`` for it the FE sees a token-less stream and shows "assistant
unavailable" while the run is already going in the background.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.streaming.mapper import stream_agent_events
from langchain_core.messages import AIMessage, AIMessageChunk


class _FakeGraph:
    """Replays scripted (ns, mode, data) tuples through ``astream``."""

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


def test_research_launcher_reply_is_streamed_as_a_token():
    reply = "Mình đã bắt đầu nghiên cứu kỹ chuyến đi của bạn."
    items = [
        ((), "updates", {"supervisor": {"language": "vi"}}),
        # The launcher's in-node translation call streams as a top-level chunk;
        # it is internal and must not leak into the reply.
        (
            (),
            "messages",
            (
                AIMessageChunk(content='{"items": ["..."]}'),
                {"langgraph_node": "research"},
            ),
        ),
        (
            (),
            "updates",
            {
                "research": {
                    "current_flow": "research",
                    "messages": [
                        AIMessage(
                            content=reply,
                            additional_kwargs={"research_started": True},
                        )
                    ],
                }
            },
        ),
    ]
    graph = _FakeGraph(items, values={"current_flow": "research"})
    out = _run(graph)

    tokens = [d["content"] for n, d in out if n == "token"]
    assert tokens == [reply]
    assert out[-1][0] == "done"
