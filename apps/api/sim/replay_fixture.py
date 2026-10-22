"""Replay a fixture transcript over a Bus on an ephemeral port.

Test seam for the UI smoke script (not a user-facing replay mode): it starts a
Bus on ``port=0`` so it never collides with a live ``sim-run`` on 8765, preloads
the fixture events into history, prints ``PORT=<n>`` on its first stdout line,
then blocks until a SIGTERM/SIGINT arrives while the bus replays history to any
late client. The temp run dir is cleaned up on exit.
"""

import asyncio
import json
import signal
import sys
import tempfile
from pathlib import Path

from sim.bus import Bus

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC_DIR = _REPO_ROOT / "tools" / "sim-ui"


def _load_events(path):
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            events.append(json.loads(stripped))
    return events


async def _serve(events):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    with tempfile.TemporaryDirectory(prefix="sim-replay-") as run_dir:
        bus = Bus(
            run_dir=run_dir,
            static_dir=_STATIC_DIR,
            port=0,
        )
        await bus.start()
        try:
            for event in events:
                await bus.publish(event)
            print(f"PORT={bus.port}", flush=True)
            await stop.wait()
        finally:
            await bus.stop()


def main(argv):
    if len(argv) != 2:
        print(
            "usage: python -m sim.replay_fixture <transcript.jsonl>",
            file=sys.stderr,
        )
        return 2
    asyncio.run(_serve(_load_events(argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
