"""SC-10 progress bus + research SSE schema: publish-order delivery, ring-buffer
replay for a late subscriber, ``close`` ending the iterator, and no ``content``/
``args`` leakage in serialised tool/file payloads."""

from __future__ import annotations

import json

import pytest
from app.research.progress import ProgressBus
from app.streaming.research_events import (
    ResearchFile,
    ResearchTool,
    derive_events,
)


@pytest.mark.asyncio
async def test_events_arrive_in_publish_order() -> None:
    bus = ProgressBus()
    for i in range(3):
        bus.publish("run-1", {"seq": i})

    received = []
    async for event in bus.subscribe("run-1"):
        received.append(event)
        if len(received) == 3:
            bus.close("run-1")

    assert received == [{"seq": 0}, {"seq": 1}, {"seq": 2}]


@pytest.mark.asyncio
async def test_late_subscriber_replays_ring_buffer_then_live() -> None:
    bus = ProgressBus()
    for i in range(3):
        bus.publish("run-2", {"seq": i})

    received = []
    agen = bus.subscribe("run-2")
    # Replay of the 3 buffered events must come first.
    for _ in range(3):
        received.append(await agen.__anext__())
    assert received == [{"seq": 0}, {"seq": 1}, {"seq": 2}]

    # A 4th, live-published event follows the replay.
    bus.publish("run-2", {"seq": 3})
    received.append(await agen.__anext__())
    assert received[-1] == {"seq": 3}

    await agen.aclose()


@pytest.mark.asyncio
async def test_close_ends_iterator_and_clears_state() -> None:
    bus = ProgressBus()
    bus.publish("run-3", {"seq": 0})
    assert bus.has("run-3") is True

    agen = bus.subscribe("run-3")
    assert await agen.__anext__() == {"seq": 0}

    bus.close("run-3")
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    assert bus.has("run-3") is False


def test_tool_and_file_events_leak_no_content_or_args() -> None:
    # A realistic write_file astream_events(v3) item — carries content + args.
    v3_event = {
        "event": "on_tool_end",
        "name": "write_file",
        "data": {
            "input": {
                "file_path": "/research/flights.md",
                "content": "SECRET dossier prose the client must never see",
            },
            "output": "ok",
        },
    }
    events = derive_events(v3_event)
    kinds = {type(e) for e in events}
    assert ResearchTool in kinds and ResearchFile in kinds

    for event in events:
        payload = json.loads(event.to_sse().data)
        assert "content" not in payload
        assert "args" not in payload
        assert "SECRET" not in event.to_sse().data

    file_event = next(e for e in events if isinstance(e, ResearchFile))
    assert file_event.path == "/research/flights.md"
    assert file_event.bytes > 0


def test_unrecognized_event_maps_to_empty() -> None:
    assert derive_events({"event": "on_chat_model_stream", "data": {}}) == []
    assert derive_events({}) == []
