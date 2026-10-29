"""RedisProgressBus must not stall the event loop when Redis is slow or down."""

from __future__ import annotations

import asyncio
import time

from app.research.progress import RedisProgressBus
from app.streaming.research_events import ResearchFile

SLOW_S = 0.3


class _SlowRedis:
    """Stands in for a hung Redis: every call blocks, then fails."""

    def __init__(self) -> None:
        self.calls = 0

    def _fail(self, *_a, **_k):
        self.calls += 1
        time.sleep(SLOW_S)
        raise ConnectionError("redis down")

    get = set = _fail

    def pipeline(self):
        return self

    def register_script(self, _src):
        return self._fail


def _bus() -> tuple[RedisProgressBus, _SlowRedis]:
    bus = RedisProgressBus("redis://localhost:1/0", live_ttl_s=60)
    fake = _SlowRedis()
    bus._r = fake  # type: ignore[assignment]
    bus._publish_script = fake._fail  # type: ignore[assignment]
    return bus, fake


def test_publish_from_event_loop_does_not_block_it() -> None:
    bus, _ = _bus()

    async def go() -> float:
        start = time.monotonic()
        for _ in range(5):
            bus.publish("r1", ResearchFile(path="/a.md", bytes=1))
        return time.monotonic() - start

    assert asyncio.run(go()) < SLOW_S / 2


def test_circuit_breaker_skips_redis_after_failure() -> None:
    bus, fake = _bus()

    assert bus.has("r1") is False  # first call pays the failure
    calls = fake.calls
    start = time.monotonic()
    for _ in range(5):
        assert bus.has("r1") is False
        bus.open("r1")
    assert fake.calls == calls
    assert time.monotonic() - start < SLOW_S / 2


def test_open_from_event_loop_does_not_block_it() -> None:
    bus, _ = _bus()

    async def go() -> float:
        start = time.monotonic()
        for i in range(5):
            bus.open(f"r{i}")
        return time.monotonic() - start

    assert asyncio.run(go()) < SLOW_S / 2


class _FlakyRedis:
    """Fails until ``healthy`` is set; records successful writes."""

    def __init__(self) -> None:
        self.healthy = False
        self.sets: list[tuple] = []
        self.scripts = 0
        self.state: str | None = None

    def set(self, *a, **k):
        if not self.healthy:
            raise ConnectionError("redis down")
        self.sets.append((a, k))

    def get(self, *_a, **_k):
        return self.state

    def script(self, **_k):
        self.scripts += 1
        return 1


def test_skipped_open_is_retried_on_next_publish() -> None:
    bus = RedisProgressBus("redis://localhost:1/0", live_ttl_s=60)
    fake = _FlakyRedis()
    bus._r = fake  # type: ignore[assignment]
    bus._publish_script = fake.script  # type: ignore[assignment]

    bus.open("r1")  # fails, opens the breaker
    assert fake.sets == []
    fake.healthy = True
    bus._down_until = 0.0  # breaker window elapsed
    bus.publish("r1", ResearchFile(path="/a.md", bytes=1))

    assert len(fake.sets) == 1  # the open was retried before the publish
    assert fake.scripts == 1
    assert "r1" not in bus._unopened


def test_has_is_false_right_after_close() -> None:
    bus = RedisProgressBus("redis://localhost:1/0", live_ttl_s=60)
    fake = _FlakyRedis()
    fake.healthy = True
    fake.state = "live"
    bus._r = fake  # type: ignore[assignment]
    bus._r.pipeline = lambda: type(  # type: ignore[method-assign]
        "P", (), {"__getattr__": lambda s, n: lambda *a, **k: None}
    )()

    assert bus.has("r1") is True
    bus.close("r1")
    assert bus.has("r1") is False
    bus.open("r1")  # a resume re-opens the run
    assert bus.has("r1") is True


def test_shutdown_stops_io_thread() -> None:
    bus, _ = _bus()
    bus.shutdown()
    try:
        bus._io.submit(lambda: None)
    except RuntimeError:
        return
    raise AssertionError("executor still accepting work after shutdown")
