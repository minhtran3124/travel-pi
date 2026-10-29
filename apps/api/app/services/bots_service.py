"""Bots dashboard data: aggregate live ``bot_heartbeats`` rows into one entry per container.

A *bot* is one container/instance; its server processes (one heartbeat row each) are merged.
Each row's ``snapshot`` carries that process's in-flight turns (``{"turns": [...]}``); the
output is a whitelist copy with short, truncated labels, so ids and message text can never leak.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.instance import BOT_ROLES, DEFAULT_ROLE
from app.db.models import BotHeartbeat
from app.repositories.bot_heartbeat import BotHeartbeatRepository

ONLINE_WITHIN = timedelta(seconds=10)
STALE_WITHIN = timedelta(seconds=60)

MAX_TURNS_PER_BOT = 50
MAX_AGENTS_PER_TURN = 10
_LABEL_MAX = 40


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _parse(value: Any) -> datetime | None:
    """ISO-8601 string or epoch seconds -> aware datetime, else None."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if isinstance(value, str) and value:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _label(value: Any) -> str | None:
    return value[:_LABEL_MAX] if isinstance(value, str) and value else None


def _elapsed(since: Any, now: datetime) -> int:
    moment = _parse(since)
    return max(0, int((now - moment).total_seconds())) if moment else 0


def _clean_agent(raw: Any, now: datetime) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "agent": _label(raw.get("agent")) or "unknown",
        "phase": _label(raw.get("phase")),
        "tool": _label(raw.get("tool")),
        "elapsed_s": _elapsed(raw.get("since"), now),
    }


def _clean_turns(snapshot: Any, now: datetime) -> list[dict[str, Any]]:
    raw_turns = snapshot.get("turns") if isinstance(snapshot, dict) else None
    turns: list[dict[str, Any]] = []
    for raw in raw_turns if isinstance(raw_turns, list) else []:
        if not isinstance(raw, dict):
            continue
        raw_agents = raw.get("agents")
        raw_agents = raw_agents if isinstance(raw_agents, list) else []
        agents = [
            a
            for a in (_clean_agent(x, now) for x in raw_agents[:MAX_AGENTS_PER_TURN])
            if a
        ]
        turns.append(
            {
                "conv": _label(raw.get("conv")) or "",
                "kind": _label(raw.get("kind")) or "chat",
                "elapsed_s": _elapsed(raw.get("started_at"), now),
                "agents": agents,
            }
        )
    return turns


class BotsService:
    """Read-only view over live heartbeats."""

    def __init__(self, session: Session) -> None:
        self._repo = BotHeartbeatRepository(session)

    def aggregate(self, now: datetime | None = None) -> dict[str, Any]:
        """Return ``{generated_at, bots, counts}`` for rows seen in the last 60 s."""
        now = now or datetime.now(timezone.utc)
        rows = self._repo.list_live(_iso(now - STALE_WITHIN))
        groups: dict[str, list[BotHeartbeat]] = defaultdict(list)
        for row in rows:
            groups[row.instance_id].append(row)

        bots = [self._bot(iid, group, now) for iid, group in groups.items()]
        bots.sort(key=lambda b: (b["role"] != "web", b["id"]))
        return {
            "generated_at": _iso(now),
            "bots": bots,
            "counts": {
                "online": sum(b["status"] == "online" for b in bots),
                "busy": sum(
                    b["status"] == "online" and b["agent_count"] > 0 for b in bots
                ),
                "agents": sum(b["agent_count"] for b in bots),
                "turns": sum(len(b["turns"]) for b in bots),
            },
        }

    @staticmethod
    def _bot(
        instance_id: str, group: list[BotHeartbeat], now: datetime
    ) -> dict[str, Any]:
        online_cutoff = _iso(now - ONLINE_WITHIN)
        fresh = [r for r in group if r.last_seen >= online_cutoff]
        # A stale process's snapshot is out of date, so only fresh rows contribute turns.
        turns: list[dict[str, Any]] = []
        for row in fresh:
            turns.extend(_clean_turns(row.snapshot, now))
        turns = turns[:MAX_TURNS_PER_BOT]
        starts = [d for d in (_parse(r.started_at) for r in group) if d]
        role = "worker" if any(r.role == "worker" for r in group) else DEFAULT_ROLE
        return {
            "id": instance_id,
            "name": instance_id,
            "role": role if role in BOT_ROLES else DEFAULT_ROLE,
            "status": "online" if fresh else "stale",
            "processes": len(group),
            "uptime_s": (
                max(0, int((now - min(starts)).total_seconds())) if starts else 0
            ),
            "turns": turns,
            "agent_count": sum(len(t["agents"]) for t in turns),
        }
