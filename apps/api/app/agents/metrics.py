"""Per-turn LLM/token/latency instrumentation via one BaseCallbackHandler per turn.

Collection is best-effort: every hook swallows failures so they never reach the
reply path. ``cost_usd`` is filled by the owner after ``snapshot()``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import add_usage
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

#: Hard cap on per-turn step rows; past it, steps are counted in ``steps_dropped``
#: while counters and totals stay exact.
MAX_STEPS_PER_TURN = 200

#: Scalar allowlist for step ``meta``; nothing from state, tool inputs or model output.
_META_ALLOWLIST = ("finish_reason",)


def _node_key(node: str, checkpoint_ns: str) -> str:
    """Node timing key: ``"<ns_root>/<node>"`` inside a sub-graph, else the bare node.

    A ``'|'`` in ``checkpoint_ns`` marks a sub-graph, so parallel ``Send`` workers
    and same-named inner nodes do not collide.
    """
    if "|" in checkpoint_ns:
        ns_root = checkpoint_ns.split("|", 1)[0].split(":", 1)[0]
        return f"{ns_root}/{node}"
    return node


def _scalar_meta(candidate: dict[str, Any]) -> dict[str, Any]:
    """Filter a candidate ``meta`` down to allowlisted keys holding scalars."""
    return {
        key: value
        for key, value in candidate.items()
        if key in _META_ALLOWLIST and isinstance(value, (str, int, float, bool))
    }


class TurnMetricsHandler(BaseCallbackHandler):
    """Collect token / latency / node-timing metrics for a single agent turn.

    Thread-safe (tools run in worker threads) via a ``threading.Lock``;
    ``run_inline`` keeps sync hooks on the event-loop thread for async runs.
    """

    run_inline = True
    raise_error = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Turn wall-clock origin; ``close_if_open`` falls back to it when a failure
        # path never reached the owner's explicit ``close(started)``.
        self._created = time.monotonic()
        self.llm_calls = 0
        self.llm_errors = 0
        self.latency_ms: int | None = None
        self.cost_usd: float | None = None
        self._usage: dict[str, Any] = {}  # model -> UsageMetadata
        self._model_calls: dict[str, int] = {}  # model -> call count
        self._nodes: dict[str, dict[str, int]] = {}  # key -> {ms, runs}
        self._llm_starts: dict[UUID, float] = {}  # run_id -> monotonic start
        self._run_models: dict[UUID, str] = {}  # run_id -> model (from start)
        # run_id -> (key, checkpoint_ns, start)
        self._node_starts: dict[UUID, tuple[str, str, float]] = {}
        self._seen_ns: set[str] = set()  # deduped checkpoint namespaces
        self._steps: list[dict[str, Any]] = []
        self.steps_dropped = 0
        self._open_steps: dict[tuple[str, UUID], int] = {}  # (kind, run_id) -> index

    # -- step plumbing ---------------------------------------------------

    def _open_step(self, kind: str, run_id: UUID, **fields: Any) -> None:
        """Append a step in START order (caller holds ``self._lock``); ``seq`` and
        ``offset_ms`` assigned here so a node span sorts above the children it brackets."""
        if len(self._steps) >= MAX_STEPS_PER_TURN:
            self.steps_dropped += 1
            return
        step: dict[str, Any] = {
            "seq": len(self._steps),
            "kind": kind,
            "node": None,
            "ns": None,
            "model": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "offset_ms": int((time.monotonic() - self._created) * 1000),
            "ms": 0,
            "status": "open",
            "error_type": None,
            "tool_name": None,
            "specialist": None,
            "meta": {},
            "_started": time.monotonic(),
        }
        step.update(fields)
        self._open_steps[(kind, run_id)] = len(self._steps)
        self._steps.append(step)

    def _close_step(
        self,
        kind: str,
        run_id: UUID,
        *,
        status: str,
        error_type: str | None = None,
        **fields: Any,
    ) -> None:
        """Fill ``ms``/``status`` on an open step. Caller must hold ``self._lock``."""
        index = self._open_steps.pop((kind, run_id), None)
        if index is None:
            return
        step = self._steps[index]
        step["ms"] = int((time.monotonic() - step["_started"]) * 1000)
        step["status"] = status
        step["error_type"] = error_type
        for key, value in fields.items():
            if value is not None:
                step[key] = value

    def steps(self) -> list[dict[str, Any]]:
        """The turn's steps in start order."""
        with self._lock:
            return [
                {k: v for k, v in step.items() if not k.startswith("_")}
                for step in self._steps
            ]

    # -- LLM hooks -------------------------------------------------------

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: Any,
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            meta = metadata or {}
            with self._lock:
                self._llm_starts[run_id] = time.monotonic()
                name = meta.get("ls_model_name")
                if name:
                    self._run_models[run_id] = name
                self._open_step(
                    "llm",
                    run_id,
                    node=meta.get("langgraph_node"),
                    ns=meta.get("langgraph_checkpoint_ns"),
                    model=name,
                    specialist=meta.get("specialist"),
                )
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chat_model_start failed", exc_info=True)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            with self._lock:
                self._llm_starts.pop(run_id, None)
                self.llm_calls += 1
                start_model = self._run_models.pop(run_id, None)
                try:
                    message = response.generations[0][0].message
                except (IndexError, AttributeError):
                    message = None
                if not isinstance(message, AIMessage):
                    self._close_step("llm", run_id, status="ok")
                    return
                model = message.response_metadata.get("model_name") or start_model
                usage = message.usage_metadata
                # Close before aggregating so a failing aggregate can't leave it open.
                details = (usage or {}).get("input_token_details") or {}
                finish_reason = message.response_metadata.get("finish_reason")
                self._close_step(
                    "llm",
                    run_id,
                    status="ok",
                    model=model,
                    input_tokens=(usage or {}).get("input_tokens", 0),
                    output_tokens=(usage or {}).get("output_tokens", 0),
                    cached_tokens=details.get("cache_read", 0),
                    meta=_scalar_meta({"finish_reason": finish_reason}),
                )
                if not (model and usage):
                    return
                # compute the aggregate first so a failure leaves state intact
                merged = add_usage(self._usage.get(model), usage)
                self._usage[model] = merged
                self._model_calls[model] = self._model_calls.get(model, 0) + 1
        except Exception:
            logger.debug("TurnMetricsHandler.on_llm_end failed", exc_info=True)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            with self._lock:
                self._llm_starts.pop(run_id, None)
                self.llm_errors += 1
                self._close_step(
                    "llm",
                    run_id,
                    status="error",
                    error_type=type(error).__name__,
                )
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_llm_error failed", exc_info=True)

    # -- tool hooks ------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Open a ``tool`` step. Tool arguments are never read; node attribution comes
        from this hook's own ``metadata``, not ``parent_run_id``."""
        try:
            meta = metadata or {}
            name = (serialized or {}).get("name") or kwargs.get("name")
            with self._lock:
                self._open_step(
                    "tool",
                    run_id,
                    node=meta.get("langgraph_node"),
                    ns=meta.get("langgraph_checkpoint_ns"),
                    tool_name=name,
                    specialist=meta.get("specialist"),
                )
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_tool_start failed", exc_info=True)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """Close the tool step. ``output`` is tool content and is never read."""
        try:
            with self._lock:
                self._close_step("tool", run_id, status="ok")
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_tool_end failed", exc_info=True)

    def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        """Close the tool step as failed. Only the exception type is recorded, since
        ``str(error)`` can quote user input."""
        try:
            with self._lock:
                self._close_step(
                    "tool",
                    run_id,
                    status="error",
                    error_type=type(error).__name__,
                )
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_tool_error failed", exc_info=True)

    # -- graph node hooks ------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: Any,
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            meta = metadata or {}
            node = meta.get("langgraph_node")
            if not node:
                return
            ns = meta.get("langgraph_checkpoint_ns") or ""
            with self._lock:
                if ns in self._seen_ns:
                    return
                self._seen_ns.add(ns)
                self._node_starts[run_id] = (
                    _node_key(node, ns),
                    ns,
                    time.monotonic(),
                )
                # Node span carries the specialist so its row and the LLM row inside
                # it attribute to the same prompts.
                self._open_step(
                    "node", run_id, node=node, ns=ns, specialist=meta.get("specialist")
                )
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chain_start failed", exc_info=True)

    def _close_node(
        self, run_id: UUID, *, status: str, error_type: str | None = None
    ) -> None:
        with self._lock:
            self._close_step("node", run_id, status=status, error_type=error_type)
            entry = self._node_starts.pop(run_id, None)
            if entry is None:
                return
            key, ns, started = entry
            # Release the namespace once the outermost run for this task closes, so a
            # genuine re-execution (a RetryPolicy retry reuses the ns) is timed again.
            self._seen_ns.discard(ns)
            ms = int((time.monotonic() - started) * 1000)
            slot = self._nodes.setdefault(key, {"ms": 0, "runs": 0})
            slot["ms"] += ms
            slot["runs"] += 1

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """Close the node step. ``outputs`` is graph state (it carries ``messages``)
        and is never read."""
        try:
            self._close_node(run_id, status="ok")
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chain_end failed", exc_info=True)

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            self._close_node(run_id, status="error", error_type=type(error).__name__)
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chain_error failed", exc_info=True)

    # -- lifecycle / output ----------------------------------------------

    def close(self, started: float) -> None:
        """Set turn wall-clock ``latency_ms`` from an owner-held ``time.monotonic()``."""
        self.latency_ms = int((time.monotonic() - started) * 1000)

    def close_if_open(self) -> None:
        """Close the turn from creation time if not closed yet, so a failed turn still
        records a real ``latency_ms`` instead of dropping out of the rollups."""
        if self.latency_ms is None:
            self.latency_ms = int((time.monotonic() - self._created) * 1000)
        self._sweep_open_steps()

    def _sweep_open_steps(self) -> None:
        """Close any step still open when the turn ends (a cancelled stream or reused
        ``run_id`` can strand one), giving it its reached duration and a terminal status."""
        try:
            with self._lock:
                now = time.monotonic()
                for index in self._open_steps.values():
                    step = self._steps[index]
                    if step.get("status") == "open":
                        step["status"] = "unfinished"
                        step["ms"] = max(
                            0,
                            int(now * 1000)
                            - int(self._created * 1000)
                            - step["offset_ms"],
                        )
                self._open_steps.clear()
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler._sweep_open_steps failed", exc_info=True)

    def snapshot(self) -> dict[str, Any]:
        """Full server-side metrics dict (``cost_usd`` filled by the owner)."""
        with self._lock:
            by_model: dict[str, dict[str, int]] = {}
            for model, um in self._usage.items():
                details = um.get("input_token_details") or {}
                by_model[model] = {
                    "input_tokens": um.get("input_tokens", 0),
                    "output_tokens": um.get("output_tokens", 0),
                    "cached_tokens": details.get("cache_read", 0),
                    "calls": self._model_calls.get(model, 0),
                }
            input_tokens = sum(m["input_tokens"] for m in by_model.values())
            output_tokens = sum(m["output_tokens"] for m in by_model.values())
            cached_tokens = sum(m["cached_tokens"] for m in by_model.values())
            return {
                "llm_calls": self.llm_calls,
                "llm_errors": self.llm_errors,
                "latency_ms": self.latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": input_tokens + output_tokens,
                "by_model": by_model,
                "by_node": {k: dict(v) for k, v in self._nodes.items()},
                "cost_usd": self.cost_usd,
            }

    def public(self) -> dict[str, Any]:
        """Client-facing subset (no per-node breakdown)."""
        snap = self.snapshot()
        return {
            "input_tokens": snap["input_tokens"],
            "output_tokens": snap["output_tokens"],
            "cached_tokens": snap["cached_tokens"],
            "total_tokens": snap["total_tokens"],
            "llm_calls": snap["llm_calls"],
            "latency_ms": snap["latency_ms"],
            "cost_usd": snap["cost_usd"],
            "models": sorted(snap["by_model"].keys()),
        }
