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
        """True only while the run is still live here. A finished run keeps a
        closed tombstone so a late subscriber can be told "not live" instead of
        parking on a queue forever — but ``has`` reports it as gone, so the SSE
        endpoint takes the DB-snapshot branch."""
        channel = self._runs.get(run_id)
        return channel is not None and not channel.closed

    def _channel(self, run_id: str) -> _RunChannel:
        channel = self._runs.get(run_id)
        if channel is None:
            channel = self._runs[run_id] = _RunChannel()
        return channel

    def open(self, run_id: str) -> None:
        """Make a just-booked run live before its runner publishes anything, so an
        SSE client that connects on the 202 tails it instead of taking the snapshot
        branch. A closed tombstone stays closed."""
        self._channel(run_id)

    def publish(self, run_id: str, event: Any) -> None:
        channel = self._channel(run_id)
        if channel.closed:
            # Never resurrect a finished run: its subscribers are gone and its
            # tombstone is what tells a late one to use the snapshot instead.
            return
        channel.buffer.append(event)
        for queue in channel.queues:
            queue.put_nowait(event)

    async def subscribe(self, run_id: str) -> AsyncIterator[Any]:
        # A subscriber may legitimately arrive before the first publish (the SSE
        # endpoint opens while the runner is still starting), so an absent channel
        # is created live. An already-closed one is not: there is nothing left to
        # tail and no sentinel would ever arrive, so the caller falls back to the
        # DB snapshot, which is what a late viewer should get.
        channel = self._channel(run_id)
        if channel.closed:
            return
        queue: asyncio.Queue[Any] = asyncio.Queue()
        replay = list(channel.buffer)
        channel.queues.add(queue)
        try:
            for event in replay:
                yield event
            # Deliberately no ``if channel.closed: return`` here. Each ``yield``
            # above suspends, so the run can finish mid-replay — publishing its
            # terminal event into ``queue`` and closing. Stopping on the flag would
            # drop that event and end the SSE stream with no terminal frame, which
            # the client reads as a failed run. ``close`` posts the sentinel, so
            # draining the queue below always terminates.
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    return
                yield event
        finally:
            channel.queues.discard(queue)

    def close(self, run_id: str) -> None:
        """End the run's live stream: wake every subscriber with the sentinel and
        release the buffered events. The channel object itself is kept as a closed
        tombstone (a couple of empty containers, not the ~200 buffered events that
        made this leak) so a later ``subscribe`` can tell "finished" from "never
        started" and decline instead of parking forever."""
        channel = self._runs.get(run_id)
        if channel is None or channel.closed:
            return
        channel.closed = True
        for queue in channel.queues:
            queue.put_nowait(_SENTINEL)
        channel.queues.clear()
        channel.buffer.clear()
