"""Research-agent long-term memory: `/memory/AGENTS.md` seeding and a write guard.

The research agent's `/memory/` route is a per-user ``StoreBackend`` scoped to the
``("users", <uid>, "research_memory")`` namespace (design §2). Two pieces live here:

- :func:`seed_agents_md` writes an initial `AGENTS.md` from the traveller's existing
  preference store so the first run is not cold, then hands ownership to the agent.
- :class:`GuardedStoreBackend` runs the chat memory guard's content rules on every
  write so injection text smuggled into research memory cannot be persisted (design §3).

This module *reuses* ``app.memory.guard`` / ``app.memory.store`` — it never re-implements
them, so the chat memory path stays the single source of truth for the guard rules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from deepagents.backends.protocol import EditResult, WriteResult
from deepagents.backends.store import StoreBackend
from langgraph.store.base import BaseStore

from app.memory.guard import MemoryRejected, check_content
from app.memory.store import MemoryKind, search_memory_typed

# The composite backend strips the ``/memory/`` route prefix before delegating, so the
# key the agent reads (`memory=["/memory/AGENTS.md"]`) resolves to ``/AGENTS.md`` inside
# this namespace-scoped store (deepagents composite `_route_for_path`).
AGENTS_MD_PATH = "/AGENTS.md"

# Third namespace component for the research memory route (design §2). Kept distinct from
# the chat memory namespaces (``prefs``/``procedural``/``episodes``).
RESEARCH_MEMORY_KIND = "research_memory"

# A shape-valid synthetic key so the guard scans content (a real filename with a dot would
# fail the guard's key-shape rule before the content is ever checked).
_GUARD_KEY = "research_memory"

_TITLE = "# Traveller research memory"

# Reproduces the MIN-65 D2 preference block header verbatim.
_PREF_BLOCK_HEADER = (
    "Traveller preferences (learned from past conversations — use to personalise,\n"
    "confirm before acting on stale ones):"
)

_EMPTY_BODY = "(No stored preferences yet.)"


def _research_memory_namespace(
    user_id: str,
) -> Callable[[Any], tuple[str, ...]]:
    return lambda _rt: ("users", user_id, RESEARCH_MEMORY_KIND)


def seed_agents_md(store: BaseStore, user_id: str) -> None:
    """Seed `/memory/AGENTS.md` from the preference store; no-op if it already exists.

    Idempotent: once the file is present the agent owns it, so a later call returns
    without touching it. With no stored preferences a minimal valid file (title +
    header + a "none yet" line) is still written, so the agent always has a readable,
    appendable memory file rather than a missing one.
    """
    backend = StoreBackend(
        store=store,
        namespace=_research_memory_namespace(user_id),
    )
    if backend.read(AGENTS_MD_PATH).error is None:
        return

    # ``search_memory_typed`` (not ``search_preferences``) because the D2 line is
    # ``- <key>: <text>`` and ``search_preferences`` discards the store key.
    preferences = search_memory_typed(store, user_id, MemoryKind.PREFERENCES)
    lines = [f"- {pref.key}: {pref.text}" for pref in preferences]
    body = "\n".join(lines) if lines else _EMPTY_BODY
    content = f"{_TITLE}\n\n{_PREF_BLOCK_HEADER}\n{body}\n"
    backend.upload_files([(AGENTS_MD_PATH, content.encode("utf-8"))])


class GuardedStoreBackend(StoreBackend):
    """`StoreBackend` that rejects writes carrying an injection phrase.

    Runs the chat memory guard's content rules (:func:`app.memory.guard.check_content`)
    on the text being written; a blocklist hit is surfaced as a deepagents-style
    permission-denied error the model can read. Length caps and key allowlists (chat
    memory concerns, not document concerns) do not apply — only injection is blocked.
    Reads and every non-write operation are inherited unchanged.
    """

    def _guard_rejection(self, content: str, file_path: str) -> str | None:
        try:
            check_content("instructions", _GUARD_KEY, content)
        except MemoryRejected as exc:
            # Only an injection phrase denies the write; ``empty`` and length concerns
            # are irrelevant for a free-form memory document.
            if exc.reason.startswith("blocked_pattern"):
                return (
                    f"Error: permission denied for write on {file_path} ({exc.reason})"
                )
        return None

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        rejection = self._guard_rejection(content, file_path)
        if rejection is not None:
            return WriteResult(error=rejection)
        return super().write(file_path, content)

    async def awrite(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        rejection = self._guard_rejection(content, file_path)
        if rejection is not None:
            return WriteResult(error=rejection)
        return await super().awrite(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        rejection = self._guard_rejection(new_string, file_path)
        if rejection is not None:
            return EditResult(error=rejection)
        return super().edit(file_path, old_string, new_string, replace_all)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        rejection = self._guard_rejection(new_string, file_path)
        if rejection is not None:
            return EditResult(error=rejection)
        return await super().aedit(file_path, old_string, new_string, replace_all)
