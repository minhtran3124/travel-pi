import asyncio
import json

import pytest
from sim.bus import Bus
from websockets.asyncio.client import connect

INDEX_HTML = "<!doctype html><title>sim</title><h1>sim ui</h1>"


async def _http_get(
    port,
    path,
):
    reader, writer = await asyncio.open_connection("localhost", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    return status, body.decode()


async def _scenario(
    run_dir,
    static_dir,
):
    bus = Bus(run_dir, static_dir, port=0)
    await bus.start()
    try:
        url = f"ws://localhost:{bus.port}/ws"
        async with connect(url) as c1, connect(url) as c2:
            await asyncio.sleep(0.05)
            events = [
                {"type": "batch_start", "persona_id": None, "v": 1},
                {"type": "walk_to_desk", "persona_id": "p1", "seat": 0},
                {"type": "user_say", "persona_id": "p1", "text": "hi"},
            ]
            for event in events:
                await bus.publish(event)

            got1 = [json.loads(await c1.recv()) for _ in range(3)]
            got2 = [json.loads(await c2.recv()) for _ in range(3)]

            async with connect(url) as c3:
                got3 = [json.loads(await c3.recv()) for _ in range(3)]

        ok_status, body = await _http_get(bus.port, "/")
        missing_status, _ = await _http_get(bus.port, "/nope.html")
        traversal_status, _ = await _http_get(bus.port, "/../secret.txt")
        return got1, got2, got3, ok_status, body, missing_status, traversal_status
    finally:
        await bus.stop()


def test_bus_fanout_history_transcript_and_static(tmp_path):
    run_dir = tmp_path / "run"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(INDEX_HTML)

    result = asyncio.run(_scenario(run_dir, static_dir))
    got1, got2, got3, ok_status, body, missing_status, traversal_status = result

    assert [e["type"] for e in got1] == ["batch_start", "walk_to_desk", "user_say"]
    assert [e["type"] for e in got2] == ["batch_start", "walk_to_desk", "user_say"]
    assert [e["type"] for e in got3] == ["batch_start", "walk_to_desk", "user_say"]
    assert all("t" in e for e in got1)

    lines = (run_dir / "transcript.jsonl").read_text().splitlines()
    assert len(lines) == 3

    assert ok_status == 200
    assert body == INDEX_HTML
    assert missing_status == 404
    assert traversal_status == 404


async def _race_scenario(
    run_dir,
    static_dir,
    n,
):
    bus = Bus(run_dir, static_dir, port=0)
    snapshots = []
    bus.on_register = snapshots.append
    await bus.start()
    try:
        url = f"ws://localhost:{bus.port}/ws"

        async def publisher():
            for i in range(n):
                await bus.publish({"type": "e", "persona_id": None, "i": i})
                await asyncio.sleep(0)

        pub_task = asyncio.create_task(publisher())
        async with connect(url) as ws:
            got = [json.loads(await ws.recv())["i"] for _ in range(n)]
        await pub_task
        return got, snapshots[-1]
    finally:
        await bus.stop()


def test_late_client_gets_each_event_once_in_order(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    n = 50
    for attempt in range(10):
        run_dir = tmp_path / f"run{attempt}"
        got, snapshot = asyncio.run(_race_scenario(run_dir, static_dir, n))
        assert got == list(range(n))
        if 0 < snapshot < n:
            break
    else:
        raise AssertionError(
            f"mid-flight registration window never hit; snapshot stayed at {snapshot}"
        )


def test_publish_before_start_raises(tmp_path):
    bus = Bus(tmp_path / "run", tmp_path / "static", port=0)
    with pytest.raises(RuntimeError):
        asyncio.run(bus.publish({"type": "e", "persona_id": None}))


async def _start_stop_then_publish(run_dir, static_dir):
    bus = Bus(run_dir, static_dir, port=0)
    await bus.start()
    await bus.stop()
    await bus.publish({"type": "e", "persona_id": None})


def test_publish_after_stop_raises(tmp_path):
    (tmp_path / "static").mkdir()
    with pytest.raises(RuntimeError):
        asyncio.run(_start_stop_then_publish(tmp_path / "run", tmp_path / "static"))
