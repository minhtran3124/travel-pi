"""In-process progress bus: ``run_id`` → (ring buffer, live subscriber queues).

A background research run ``publish``es derived progress events; a later-opened SSE
connection ``subscribe``s and first replays the last ``RING_BUFFER_SIZE`` events
(so it never misses what happened before it connected) then tails live publishes.
``close`` ends every active subscriber iterator for a run and drops its state;
``has`` reports whether the bus still holds state for a run (design §4). Per-process
and non-durable by design — the SSE route falls back to a DB snapshot when the bus
has no channel for a run. With ``REDIS_URL`` set, :class:`RedisProgressBus` (built by
:func:`make_progress_bus`) offers the same interface across processes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from typing import Any

logger = logging.getLogger(__name__)

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


# -- Redis-backed bus (specs/prod-deploy-render-concurrency, Task 6) -----------

_REDIS_PUBLISH_LUA = """
if redis.call('GET', KEYS[1]) == 'closed' then return 0 end
local seq = redis.call('INCR', KEYS[2])
local msg = '{"seq":' .. seq .. ',"e":' .. ARGV[1] .. '}'
redis.call('SET', KEYS[1], 'live', 'EX', ARGV[2])
redis.call('RPUSH', KEYS[3], msg)
redis.call('LTRIM', KEYS[3], -tonumber(ARGV[3]), -1)
redis.call('EXPIRE', KEYS[3], ARGV[2])
redis.call('EXPIRE', KEYS[2], ARGV[2])
redis.call('PUBLISH', KEYS[4], msg)
return seq
"""

#: How long a closed tombstone survives (stops a late publish resurrecting a run).
_CLOSED_TTL_S = 3600
_POLL_S = 1.0
#: After a Redis failure, skip Redis entirely for this long (circuit breaker), so a
#: down Redis costs one timeout per window instead of one per event.
_BREAKER_COOLDOWN_S = 5.0


def _encode_event(event: Any) -> str | None:
    if not (is_dataclass(event) and not isinstance(event, type)):
        return None
    return json.dumps({"t": type(event).__name__, "d": asdict(event)})


def _decode_event(raw: dict[str, Any]) -> Any | None:
    from app.streaming import research_events

    cls = getattr(research_events, str(raw.get("t")), None)
    if not (isinstance(cls, type) and issubclass(cls, research_events.ResearchEvent)):
        return None
    return cls(**raw["d"])


class RedisProgressBus(ProgressBus):
    """``ProgressBus`` whose state lives in Redis so any web instance can tail a run
    driven by another process (the Arq worker, or a different instance).

    Per run: ``state`` (``live`` with a TTL, or a ``closed`` tombstone), a capped
    ring-buffer list for replay, and a pub/sub channel for the live tail. A
    subscriber subscribes first, then replays the list, then dedupes the tail by a
    per-run sequence number, so nothing is missed or doubled. Redis is not a source
    of truth: every failure degrades to "not live", which sends the SSE route to the
    DB-snapshot branch.
    """

    def __init__(self, url: str, *, live_ttl_s: int) -> None:
        import redis

        super().__init__()
        self._url = url
        self._ttl = live_ttl_s
        self._r = redis.Redis.from_url(
            url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )
        self._down_until = 0.0
        # One thread keeps publish/close ordered while keeping their blocking
        # socket I/O off the event loop.
        self._io = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="progress-redis"
        )
        self._publish_script = self._r.register_script(_REDIS_PUBLISH_LUA)

    @staticmethod
    def _key(run_id: str, part: str) -> str:
        return f"research:{{{run_id}}}:{part}"

    def _guarded(self, name: str, fn: Callable[[], Any], default: Any = None) -> Any:
        """Run one Redis call behind the circuit breaker; any failure opens it."""
        if time.monotonic() < self._down_until:
            return default
        try:
            return fn()
        except Exception:  # noqa: BLE001 — Redis is best-effort, never fatal
            self._down_until = time.monotonic() + _BREAKER_COOLDOWN_S
            logger.warning("[progress] redis %s failed", name, exc_info=True)
            return default

    def _fire(self, name: str, fn: Callable[[], Any]) -> None:
        """Fire-and-forget write: off the event loop when there is one (ordered via
        the single IO thread), inline otherwise (sync callers, tests)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._guarded(name, fn)
            return
        self._io.submit(self._guarded, name, fn)

    def has(self, run_id: str) -> bool:
        return self._guarded(
            "has()", lambda: self._r.get(self._key(run_id, "state")) == "live", False
        )

    def open(self, run_id: str) -> None:
        self._guarded(
            "open()",
            lambda: self._r.set(
                self._key(run_id, "state"), "live", nx=True, ex=self._ttl
            ),
        )

    def publish(self, run_id: str, event: Any) -> None:
        encoded = _encode_event(event)
        if encoded is None:
            logger.warning("[progress] unserialisable event %r dropped", type(event))
            return
        self._fire(
            "publish()",
            lambda: self._publish_script(
                keys=[self._key(run_id, p) for p in ("state", "seq", "buf", "chan")],
                args=[encoded, self._ttl, RING_BUFFER_SIZE],
            ),
        )

    def close(self, run_id: str) -> None:
        def _close() -> None:
            pipe = self._r.pipeline()
            pipe.set(self._key(run_id, "state"), "closed", ex=_CLOSED_TTL_S)
            pipe.delete(self._key(run_id, "buf"), self._key(run_id, "seq"))
            pipe.publish(self._key(run_id, "chan"), '{"close":true}')
            pipe.execute()

        self._fire("close()", _close)

    async def subscribe(self, run_id: str) -> AsyncIterator[Any]:
        import redis.asyncio as aredis

        r = aredis.Redis.from_url(
            self._url, decode_responses=True, socket_connect_timeout=2
        )
        pubsub = r.pubsub()
        state_key = self._key(run_id, "state")
        try:
            # Subscribe before reading the buffer so a publish in between is caught
            # by the tail; ``seq`` drops the overlap.
            await pubsub.subscribe(self._key(run_id, "chan"))
            if await r.get(state_key) != "live":
                return
            last = 0
            for raw in await r.lrange(self._key(run_id, "buf"), 0, -1):
                msg = json.loads(raw)
                last = max(last, msg["seq"])
                event = _decode_event(msg["e"])
                if event is not None:
                    yield event
            while True:
                item = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=_POLL_S
                )
                if item is None:
                    if await r.get(state_key) != "live":
                        return  # closed/expired and the close frame was missed
                    continue
                msg = json.loads(item["data"])
                if msg.get("close"):
                    return
                if msg["seq"] <= last:
                    continue
                last = msg["seq"]
                event = _decode_event(msg["e"])
                if event is not None:
                    yield event
        except Exception:  # noqa: BLE001 — caller falls back to the DB snapshot
            logger.warning("[progress] redis subscribe failed", exc_info=True)
        finally:
            try:
                await pubsub.aclose()
                await r.aclose()
            except Exception:  # noqa: BLE001
                pass


def make_progress_bus() -> ProgressBus:
    """Redis-backed when ``REDIS_URL`` is set, else the in-process bus (zero-config)."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.redis_url:
        # Outlive a full run (matches the worker's job_timeout) so a quiet phase
        # never reads as an orphan; a killed worker's key expires after this.
        return RedisProgressBus(
            settings.redis_url, live_ttl_s=settings.research_timeout_s + 120
        )
    return ProgressBus()
