"""Live registry of in-flight agent turns on this process, plus the callback handler that feeds it.

Memory only: nothing here touches the database (the chat path must stay write-free). The
heartbeat task reads ``snapshot()`` and ships it inside the ``bot_heartbeats`` row, so the
Bots page can show which agents are working inside which bot and in what phase.

Phases follow the graph: ``classify`` (guardrail, context, summarize, supervisor) ->
``specialist`` (planner, concierge, journal, booking, budget, research, synthesis workers)
-> ``tools`` (while a tool runs) -> ``reflection``. The snapshot is JSON-safe and capped; it
never carries message text, tool arguments, or full user/conversation/run ids.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from app.agents.constants import ALL_SUBAGENTS

logger = logging.getLogger(__name__)

#: Caps keep the heartbeat row small no matter how busy the process is.
MAX_TURNS = 50
MAX_AGENTS_PER_TURN = 8
#: Backstop for a turn whose end hook never fired (a killed task); a live research turn is
#: bounded by ``research_timeout_s`` (600 s), so twice that is safely beyond any real turn.
MAX_TURN_AGE_SECONDS = 1200
#: A finished chat conversation stays listed ("idle session") this long after its last turn, so the
#: Bots page keeps a chatting user visible between messages; ``LiveRegistry.idle_seconds`` overrides it.
SESSION_IDLE_SECONDS = 600
MAX_SESSIONS = 50
#: Turn kinds that belong to a chat conversation (research jobs are not sessions).
SESSION_KINDS = ("chat", "stream")
SHORT_ID_LENGTH = 8
SHORT_CONV_LENGTH = 6
MAX_TOOL_NAME_LENGTH = 48

PHASE_CLASSIFY = "classify"
PHASE_SPECIALIST = "specialist"
PHASE_TOOLS = "tools"
PHASE_REFLECTION = "reflection"

SUPERVISOR = "supervisor"
#: Placeholder until the specialist identity arrives (parallel workers learn it from child events).
GENERIC_SPECIALIST = "specialist"

#: Graph node -> (phase, agent name or None meaning "the node's own name", removed when it ends).
_NODE_PHASES: dict[str, tuple[str, str | None, bool]] = {
    "pii_guardrail": (PHASE_CLASSIFY, SUPERVISOR, False),
    "load_context": (PHASE_CLASSIFY, SUPERVISOR, False),
    "summarize": (PHASE_CLASSIFY, SUPERVISOR, False),
    "supervisor": (PHASE_CLASSIFY, SUPERVISOR, True),
    "plan": (PHASE_SPECIALIST, SUPERVISOR, True),
    "synthesize": (PHASE_SPECIALIST, SUPERVISOR, True),
    "reflection": (PHASE_REFLECTION, SUPERVISOR, True),
    "synthesis_worker": (PHASE_SPECIALIST, GENERIC_SPECIALIST, True),
    **dict.fromkeys(ALL_SUBAGENTS, (PHASE_SPECIALIST, None, True)),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def short_id(value: str | None) -> str:
    """First characters of an id, enough to correlate by eye, never the full value."""
    return (value or "")[:SHORT_ID_LENGTH]


def conv_label(conversation_id: str | None) -> str:
    """Short, non-reversible-enough label for a conversation (first characters only)."""
    return (conversation_id or "")[:SHORT_CONV_LENGTH]


class LiveRegistry:
    """Thread-safe map of in-flight turns -> agents -> (phase, tool, since)."""

    def __init__(self, idle_seconds: float = SESSION_IDLE_SECONDS) -> None:
        self._lock = threading.Lock()
        self._turns: dict[str, dict[str, Any]] = {}
        self._sessions: dict[
            str, dict[str, Any]
        ] = {}  # conv label -> idle chat session
        self.idle_seconds = idle_seconds

    def start_turn(self, run_id: str, conv: str, kind: str) -> None:
        """Register a turn (idempotent); the oldest turn is dropped when the cap is hit."""
        with self._lock:
            if run_id in self._turns:
                return
            if kind in SESSION_KINDS:
                self._sessions.pop(conv, None)  # the conversation is active again
            if len(self._turns) >= MAX_TURNS:
                oldest = min(self._turns, key=lambda r: self._turns[r]["started_at"])
                del self._turns[oldest]
            self._turns[run_id] = {
                "run_id": short_id(run_id),
                "conv": conv,
                "kind": kind,
                "started_at": _now_iso(),
                "_started_mono": time.monotonic(),
                "agents": {},
            }

    def finish_turn(self, run_id: str) -> None:
        """Remove a turn; unknown ids are ignored. A finished chat turn leaves an idle session behind."""
        with self._lock:
            turn = self._turns.pop(run_id, None)
            if turn is None or turn["kind"] not in SESSION_KINDS or not turn["conv"]:
                return
            if (
                turn["conv"] not in self._sessions
                and len(self._sessions) >= MAX_SESSIONS
            ):
                oldest = min(self._sessions, key=lambda c: self._sessions[c]["_mono"])
                del self._sessions[oldest]
            self._sessions[turn["conv"]] = {
                "conv": turn["conv"],
                "kind": turn["kind"],
                "idle_since": _now_iso(),
                "_mono": time.monotonic(),
            }

    def set_agent(
        self,
        run_id: str,
        key: str,
        agent: str,
        phase: str,
        tool: str | None = None,
    ) -> None:
        """Add or replace an agent (``key`` identifies it within the turn); over-cap adds are dropped."""
        with self._lock:
            turn = self._turns.get(run_id)
            if turn is None:
                return
            agents = turn["agents"]
            if key not in agents and len(agents) >= MAX_AGENTS_PER_TURN:
                return
            agents[key] = {
                "agent": agent,
                "phase": phase,
                "tool": tool,
                "since": _now_iso(),
            }

    def has_agent(self, run_id: str, key: str) -> bool:
        with self._lock:
            turn = self._turns.get(run_id)
            return bool(turn and key in turn["agents"])

    def set_phase(
        self, run_id: str, key: str, phase: str, tool: str | None = None
    ) -> None:
        """Move an existing agent to a phase (and tool); a no-op for unknown turns or agents."""
        with self._lock:
            agent = self._agent(run_id, key)
            if agent is None:
                return
            if agent["phase"] != phase or agent["tool"] != tool:
                agent["since"] = _now_iso()
            agent["phase"] = phase
            agent["tool"] = tool

    def rename_agent(self, run_id: str, key: str, name: str) -> None:
        with self._lock:
            agent = self._agent(run_id, key)
            if agent is not None:
                agent["agent"] = name

    def remove_agent(self, run_id: str, key: str) -> None:
        with self._lock:
            turn = self._turns.get(run_id)
            if turn is not None:
                turn["agents"].pop(key, None)

    def _agent(self, run_id: str, key: str) -> dict[str, Any] | None:
        turn = self._turns.get(run_id)
        return turn["agents"].get(key) if turn else None

    def snapshot(self) -> dict[str, Any]:
        """JSON-safe, capped view; stale turns and expired idle sessions are evicted first.

        ``sessions`` (idle chat conversations) is present only when non-empty.
        """
        with self._lock:
            now = time.monotonic()
            for run_id in [
                r
                for r, t in self._turns.items()
                if now - t["_started_mono"] > MAX_TURN_AGE_SECONDS
            ]:
                del self._turns[run_id]
            for conv in [
                c
                for c, sess in self._sessions.items()
                if now - sess["_mono"] > self.idle_seconds
            ]:
                del self._sessions[conv]
            sessions = [
                {k: v for k, v in sess.items() if not k.startswith("_")}
                for sess in self._sessions.values()
            ]
            turns = [
                {
                    "run_id": t["run_id"],
                    "conv": t["conv"],
                    "kind": t["kind"],
                    "started_at": t["started_at"],
                    "agents": [dict(a) for a in t["agents"].values()],
                }
                for t in self._turns.values()
            ]
        turns.sort(key=lambda t: t["started_at"])
        snap: dict[str, Any] = {"turns": turns[-MAX_TURNS:]}
        if sessions:
            sessions.sort(key=lambda sess: sess["idle_since"])
            snap["sessions"] = sessions
        return snap

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._sessions.clear()


#: Process-wide registry; the heartbeat snapshot provider reads it.
registry = LiveRegistry()


def _ns_root(namespace: str, node: str) -> str:
    """Agent key: the outermost checkpoint-namespace segment (stable across a node's sub-graph)."""
    root = (namespace or "").split("|", 1)[0]
    return root or node


class LiveTurnHandler(BaseCallbackHandler):
    """Feeds one turn's graph activity into the registry. Memory only; never raises into the turn."""

    run_inline = True
    raise_error = False

    def __init__(
        self,
        run_id: str,
        *,
        conv: str | None = None,
        kind: str = "chat",
        live: LiveRegistry | None = None,
    ) -> None:
        self._run_id = run_id
        self._conv = conv_label(conv)
        self._kind = kind
        self._live = live or registry
        self._started = False
        self._done = False
        self._nodes: dict[
            UUID, tuple[str, bool]
        ] = {}  # chain run_id -> (agent key, removed on end)
        self._tools: dict[UUID, str] = {}  # tool run_id -> agent key
        self._lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------

    def finish(self) -> None:
        """Remove the turn now (idempotent); owners call this in their ``finally`` as a backstop."""
        self._done = True
        self._live.finish_turn(self._run_id)

    # -- graph node hooks -----------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            if self._done:
                return
            with self._lock:
                if not self._started:
                    self._started = True
                    self._live.start_turn(self._run_id, self._conv, self._kind)
            meta = metadata or {}
            node = meta.get("langgraph_node")
            if not node:
                return
            key = _ns_root(meta.get("langgraph_checkpoint_ns") or "", node)
            specialist = meta.get("specialist")
            if specialist in ALL_SUBAGENTS and self._live.has_agent(self._run_id, key):
                self._live.rename_agent(self._run_id, key, specialist)
            spec = _NODE_PHASES.get(node)
            if spec is None:
                return  # inner sub-agent nodes (assistant, tools, ...) do not create agents
            phase, agent, removed = spec
            if agent is None:
                agent = node
            if agent == GENERIC_SPECIALIST and specialist in ALL_SUBAGENTS:
                agent = specialist
            if agent == SUPERVISOR:
                key = SUPERVISOR
            if self._live.has_agent(self._run_id, key):
                # Sub-graphs re-emit their parent's start; a supervisor node chain moves phase.
                if key == SUPERVISOR and run_id not in self._nodes:
                    self._live.set_phase(self._run_id, key, phase)
                    self._nodes[run_id] = (key, removed)
                return
            self._live.set_agent(self._run_id, key, agent, phase)
            self._nodes[run_id] = (key, removed)
        except Exception:  # pragma: no cover - defensive
            logger.debug("LiveTurnHandler.on_chain_start failed", exc_info=True)

    def _chain_closed(self, run_id: UUID, parent_run_id: UUID | None) -> None:
        entry = self._nodes.pop(run_id, None)
        if entry is not None and entry[1]:
            self._live.remove_agent(self._run_id, entry[0])
        if parent_run_id is None:
            self.finish()

    def on_chain_end(
        self,
        outputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """``outputs`` is graph state and is never read."""
        try:
            self._chain_closed(run_id, parent_run_id)
        except Exception:  # pragma: no cover - defensive
            logger.debug("LiveTurnHandler.on_chain_end failed", exc_info=True)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            self._chain_closed(run_id, parent_run_id)
        except Exception:  # pragma: no cover - defensive
            logger.debug("LiveTurnHandler.on_chain_error failed", exc_info=True)

    # -- tool hooks -----------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Only the tool name is read; arguments are never touched."""
        try:
            if self._done:
                return
            meta = metadata or {}
            ns = meta.get("langgraph_checkpoint_ns") or ""
            key = _ns_root(ns, meta.get("langgraph_node") or "")
            specialist = meta.get("specialist")
            if specialist in ALL_SUBAGENTS and self._live.has_agent(self._run_id, key):
                self._live.rename_agent(self._run_id, key, specialist)
            if not self._live.has_agent(self._run_id, key):
                return
            name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
            self._tools[run_id] = key
            self._live.set_phase(
                self._run_id, key, PHASE_TOOLS, str(name)[:MAX_TOOL_NAME_LENGTH]
            )
        except Exception:  # pragma: no cover - defensive
            logger.debug("LiveTurnHandler.on_tool_start failed", exc_info=True)

    def _tool_closed(self, run_id: UUID) -> None:
        key = self._tools.pop(run_id, None)
        if key is not None and key not in self._tools.values():
            self._live.set_phase(self._run_id, key, PHASE_SPECIALIST)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """``output`` is tool content and is never read."""
        try:
            self._tool_closed(run_id)
        except Exception:  # pragma: no cover - defensive
            logger.debug("LiveTurnHandler.on_tool_end failed", exc_info=True)

    def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            self._tool_closed(run_id)
        except Exception:  # pragma: no cover - defensive
            logger.debug("LiveTurnHandler.on_tool_error failed", exc_info=True)
