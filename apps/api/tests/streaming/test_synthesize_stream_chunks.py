"""A fanned-out turn must stream its whole synthesized answer (#179).

``synthesize`` runs only on multi-intent turns, and the mapper used to emit its
FIRST message chunk and suppress the rest::

    if root is None and node_name == "synthesize":
        if synthesize_answer_emitted:
            continue

The comment above that flag assumed the node produces one event because it calls
``llm.invoke()``. It does not: ``app/clients/llm.py`` builds every model with
``streaming=True`` (so OpenAI reports ``usage_metadata``), which routes ``invoke``
through ``_stream``, so LangGraph's ``messages`` mode yields the answer chunk by
chunk. The traveller saw a single character.

The dedupe it was doing is still needed — the finished message surfaces a second
time — so these tests pin BOTH halves: every chunk of the answer goes out, and a
second message for the same node does not.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.streaming.mapper import stream_agent_events
from langchain_core.messages import AIMessage

ANSWER_CHUNKS = ["I", " can put", " together the", " full Tokyo weekend."]
FULL_ANSWER = "".join(ANSWER_CHUNKS)


class _FakeGraph:
    """Yields a scripted ``astream`` sequence; mirrors tests/streaming/test_mapper_tool_event_dedup."""

    def __init__(self, items):
        self._items = items

    async def astream(self, stream_input, cfg, *, stream_mode, subgraphs, context=None):
        for item in self._items:
            yield item

    async def aget_state(self, cfg):
        return SimpleNamespace(interrupts=(), values={})


def _run(graph) -> list[tuple[str, dict]]:
    async def collect():
        out = []
        async for ev in stream_agent_events(
            graph, {"messages": []}, cfg={}, conversation_id="c1"
        ):
            out.append((ev.event, json.loads(ev.data)))
        return out

    return asyncio.run(collect())


def _synthesize_chunk(text: str, msg_id: str = "synth-1"):
    """One top-level ``messages`` item from the synthesize node.

    Top-level nodes stream with an empty namespace; the node name lives in the
    metadata, which is how the mapper identifies them.
    """
    return (
        (),
        "messages",
        (AIMessage(id=msg_id, content=text), {"langgraph_node": "synthesize"}),
    )


def _tokens(out: list[tuple[str, dict]]) -> list[str]:
    return [data["content"] for name, data in out if name == "token"]


def test_every_chunk_of_the_synthesized_answer_is_streamed():
    """The traveller must receive the whole answer, not just its first chunk."""
    out = _run(_FakeGraph([_synthesize_chunk(c) for c in ANSWER_CHUNKS]))

    assert "".join(_tokens(out)) == FULL_ANSWER, (
        "the synthesized answer was cut short on the wire — the mapper is "
        "suppressing chunks after the first again (#179)"
    )
    assert len(_tokens(out)) == len(ANSWER_CHUNKS)


def test_a_second_synthesize_message_is_still_deduped():
    """The original dedupe must survive: the finished message surfaces twice.

    Chunks of the answer carry one id; the duplicate arrives as a different
    message for the same node and must not be appended to the answer.
    """
    items = [_synthesize_chunk(c) for c in ANSWER_CHUNKS]
    items.append(_synthesize_chunk(FULL_ANSWER, msg_id="synth-duplicate"))

    out = _run(_FakeGraph(items))

    assert "".join(_tokens(out)) == FULL_ANSWER, (
        "the duplicate synthesize message was appended, doubling the answer"
    )
