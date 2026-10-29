#!/usr/bin/env python3
"""Seed demo ``bot_heartbeats`` rows so the dashboard Bots page has something to show.

Demo bots: ``api-1`` and ``api-2`` (two processes each) and ``worker``; the snapshots cover
every agent kind and phase. Rows carry ``host="demo-seed"`` so they are recognisable as demo
data. Run as a module from ``apps/api/``::

    python -m scripts.seed_bots              # write once (idempotent)
    python -m scripts.seed_bots --animate    # keep refreshing, moving agents through phases
    python -m scripts.seed_bots --clear      # remove the demo rows

Refuses to run when ``ENVIRONMENT=production``.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.repositories.bot_heartbeat import BotHeartbeatRepository

DEMO_HOST = "demo-seed"
PHASES = ("classify", "specialist", "tools", "reflection")
TOOLS = (
    "search_places",
    "get_weather",
    "search_flights",
    "list_expenses",
    "add_journal_entry",
)

#: (instance_id, role, pids)
BOTS: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("api-1", "web", (101, 102)),
    ("api-2", "web", (201, 202)),
    ("worker", "worker", (301,)),
)

#: Per process: turns of (conv label, kind, [(agent, phase offset)]); phases rotate with the tick.
_TURNS: dict[tuple[str, int], list[tuple[str, str, list[tuple[str, int]]]]] = {
    ("api-1", 101): [
        ("c1a2b3", "chat", [("supervisor", 0), ("planner", 1), ("concierge", 2)]),
        ("d4e5f6", "chat", [("supervisor", 3), ("budget", 1)]),
    ],
    ("api-1", 102): [("0a1b2c", "chat", [("supervisor", 1), ("booking", 2)])],
    ("api-2", 201): [("7c8d9e", "chat", [("supervisor", 2), ("journal", 3)])],
    ("api-2", 202): [
        ("3f4a5b", "chat", [("supervisor", 0), ("planner", 1), ("budget", 2)])
    ],
    ("worker", 301): [
        (
            "9e8d7c",
            "research",
            [("research", 1), ("research", 2), ("supervisor", 3)],
        )
    ],
}

#: Animation: ``api-2`` is skipped (goes grey, then returns) for the second half of each cycle.
CYCLE_TICKS = 16
OFFLINE_FROM_TICK = 8
OFFLINE_INSTANCE = "api-2"


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def build_snapshot(
    instance_id: str, pid: int, now: datetime, tick: int
) -> dict[str, Any]:
    """Snapshot in the live-registry shape for one demo process at ``tick``."""
    turns = []
    for number, (conv, kind, agents) in enumerate(_TURNS.get((instance_id, pid), [])):
        rows = []
        for index, (agent, offset) in enumerate(agents):
            phase = PHASES[(tick + offset) % len(PHASES)]
            tool = (
                TOOLS[(tick + index + number) % len(TOOLS)]
                if phase == "tools"
                else None
            )
            rows.append(
                {
                    "agent": agent,
                    "phase": phase,
                    "tool": tool,
                    "since": _iso(now - timedelta(seconds=2 + 3 * index)),
                }
            )
        turns.append(
            {
                "run_id": f"demo{pid}{number}",
                "conv": conv,
                "kind": kind,
                "started_at": _iso(now - timedelta(seconds=20 + 5 * number)),
                "agents": rows,
            }
        )
    return {"turns": turns}


def seed(
    repo: BotHeartbeatRepository,
    now: datetime | None = None,
    tick: int = 0,
    skip: frozenset[str] = frozenset(),
) -> int:
    """Upsert the demo rows (idempotent); instances in ``skip`` are left untouched. Returns rows written."""
    now = now or datetime.now(timezone.utc)
    started = _iso(now - timedelta(hours=2))
    written = 0
    for instance_id, role, pids in BOTS:
        if instance_id in skip:
            continue
        for pid in pids:
            repo.upsert(
                instance_id=instance_id,
                pid=pid,
                role=role,
                host=DEMO_HOST,
                started_at=started,
                last_seen=_iso(now),
                snapshot=build_snapshot(instance_id, pid, now, tick),
            )
            written += 1
    return written


def clear(repo: BotHeartbeatRepository) -> int:
    """Remove the demo rows only; returns how many keys were targeted."""
    count = 0
    for instance_id, _role, pids in BOTS:
        for pid in pids:
            repo.delete(instance_id, pid)
            count += 1
    return count


def offline_instances(tick: int) -> frozenset[str]:
    """Instances that skip their heartbeat at ``tick`` (so the page greys them out)."""
    if tick % CYCLE_TICKS >= OFFLINE_FROM_TICK:
        return frozenset({OFFLINE_INSTANCE})
    return frozenset()


def guard_environment() -> None:
    """Refuse to write demo data into a production database."""
    if get_settings().environment == "production":
        raise SystemExit("seed_bots refuses to run when ENVIRONMENT=production.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed demo bot heartbeats for the Bots page."
    )
    parser.add_argument(
        "--animate",
        action="store_true",
        help="keep refreshing and moving agents through phases",
    )
    parser.add_argument(
        "--clear", action="store_true", help="remove the demo rows and exit"
    )
    parser.add_argument(
        "--interval", type=float, default=3.0, help="seconds between animation ticks"
    )
    args = parser.parse_args(argv)

    guard_environment()
    repo = BotHeartbeatRepository(get_session_factory(get_settings().database_url))
    if args.clear:
        print(f"cleared demo bots ({clear(repo)} rows targeted)")
        return 0
    print(f"seeded {seed(repo)} demo process rows")
    if not args.animate:
        return 0
    tick = 0
    try:
        while True:
            time.sleep(args.interval)
            tick += 1
            seed(repo, tick=tick, skip=offline_instances(tick))
    except KeyboardInterrupt:
        clear(repo)
        print("stopped; demo rows cleared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
