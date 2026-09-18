"""In-process progress bus: ``run_id`` → (ring buffer, live subscriber queues).

A background research run ``publish``es derived progress events; a later-opened SSE
connection ``subscribe``s and first replays the last ``RING_BUFFER_SIZE`` events
(so it never misses what happened before it connected) then tails live publishes.
``close`` ends every active subscriber iterator for a run and drops its state;
``has`` reports whether the bus still holds state for a run (design §4). Per-process
and non-durable by design — the SSE route falls back to a DB snapshot when the bus
has no channel for a run.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

#: Most recent events replayed to a late subscriber before it tails live publishes.
RING_BUFFER_SIZE = 200

_SENTINEL = object()


class _RunChannel:
    def __init__(self) -> None:
        self.buffer: deque[Any] = deque(maxlen=RING_BUFFER_SIZE)
        self.queues: set[asyncio.Queue[Any]] = set()
        self.closed = False


class ProgressBus:
    def __init__(self) -> None:
        self._runs: dict[str, _RunChannel] = {}

    def has(self, run_id: str) -> bool:
        return run_id in self._runs

    def _channel(self, run_id: str) -> _RunChannel:
        channel = self._runs.get(run_id)
        if channel is None:
            channel = self._runs[run_id] = _RunChannel()
        return channel

    def publish(self, run_id: str, event: Any) -> None:
        channel = self._channel(run_id)
        if channel.closed:
            return
        channel.buffer.append(event)
        for queue in channel.queues:
            queue.put_nowait(event)

    async def subscribe(self, run_id: str) -> AsyncIterator[Any]:
        channel = self._channel(run_id)
        queue: asyncio.Queue[Any] = asyncio.Queue()
        replay = list(channel.buffer)
        channel.queues.add(queue)
        try:
            for event in replay:
                yield event
            if channel.closed:
                return
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    return
                yield event
        finally:
            channel.queues.discard(queue)

    def close(self, run_id: str) -> None:
        channel = self._runs.pop(run_id, None)
        if channel is None:
            return
        channel.closed = True
        for queue in channel.queues:
            queue.put_nowait(_SENTINEL)
