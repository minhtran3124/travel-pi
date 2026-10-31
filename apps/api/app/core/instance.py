"""Instance identity — which container/instance this process belongs to.

An *instance* is one container (``api-1``, ``api-2``, ``worker``); several server
processes inside it share one ``instance_id`` and differ only by ``pid``.
"""

import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone

BOT_ROLES = ("web", "worker")
DEFAULT_ROLE = "web"


@dataclass(frozen=True)
class BotIdentity:
    """Who this process is: container id, role, host, pid."""

    instance_id: str
    role: str
    host: str
    pid: int
    started_at: str


def _env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    return value or None


def resolve_identity(role: str | None = None) -> BotIdentity:
    """Resolve identity from env: ``BOT_INSTANCE_ID`` > ``RENDER_INSTANCE_ID`` > hostname.

    ``role`` (argument) beats ``BOT_ROLE``; anything other than ``web``/``worker`` falls back to ``web``.
    """
    host = socket.gethostname()
    instance_id = _env("BOT_INSTANCE_ID") or _env("RENDER_INSTANCE_ID") or host
    chosen = (role or _env("BOT_ROLE") or DEFAULT_ROLE).lower()
    return BotIdentity(
        instance_id=instance_id,
        role=chosen if chosen in BOT_ROLES else DEFAULT_ROLE,
        host=host,
        pid=os.getpid(),
        started_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    )
