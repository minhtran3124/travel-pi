import asyncio
import json

from sim.bus import Bus
from websockets.asyncio.client import connect

INDEX_HTML = "<!doctype html><title>sim</title><h1>sim ui</h1>"


async def _http_get(port, path):
    reader, writer = await asyncio.open_connection("localhost", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    return status, body.decode()


async def _scenario(run_dir, static_dir):
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

        status, body = await _http_get(bus.port, "/")
        return got1, got2, got3, status, body
    finally:
        await bus.stop()


def test_bus_fanout_history_transcript_and_static(tmp_path):
    run_dir = tmp_path / "run"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(INDEX_HTML)

    got1, got2, got3, status, body = asyncio.run(_scenario(run_dir, static_dir))

    assert [e["type"] for e in got1] == ["batch_start", "walk_to_desk", "user_say"]
    assert [e["type"] for e in got2] == ["batch_start", "walk_to_desk", "user_say"]
    assert [e["type"] for e in got3] == ["batch_start", "walk_to_desk", "user_say"]
    assert all("t" in e for e in got1)

    lines = (run_dir / "transcript.jsonl").read_text().splitlines()
    assert len(lines) == 3

    assert status == 200
    assert body == INDEX_HTML
