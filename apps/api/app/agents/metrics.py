"""Per-turn LLM/token/latency instrumentation (specs/agent-turn-metrics §4.1).

``TurnMetricsHandler`` is one ``BaseCallbackHandler`` instance per agent turn,
attached in ``_config`` next to the Langfuse handler. It counts LLM calls and
errors, aggregates ``AIMessage.usage_metadata`` per model (input / output /
cached tokens), and times each graph node keyed by its namespace root — all
from the callback stream, without touching node code.

Collection is best-effort: every hook body is wrapped so a failure logs at DEBUG
and never propagates into the reply path (``raise_error = False``). The handler
does not import pricing; ``cost_usd`` is filled by the owner after ``snapshot()``.
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


def _node_key(node: str, checkpoint_ns: str) -> str:
    """Node timing key: ``"<ns_root>/<node>"`` inside a sub-graph, else the bare node.

    LangGraph builds ``checkpoint_ns`` as ``"<parent>|<this task>"`` (each segment
    ``name:task_id``). A ``'|'`` therefore means this node runs inside a sub-graph,
    so parallel ``Send`` workers and same-named inner nodes do not collide.

    :param node: ``metadata["langgraph_node"]`` — this task's node name.
    :param checkpoint_ns: ``metadata["langgraph_checkpoint_ns"]``.
    :return: The ``by_node`` key.
    """
    if "|" in checkpoint_ns:
        ns_root = checkpoint_ns.split("|", 1)[0].split(":", 1)[0]
        return f"{ns_root}/{node}"
    return node


class TurnMetricsHandler(BaseCallbackHandler):
    """Collect token / latency / node-timing metrics for a single agent turn.

    Thread-safe (tools run in worker threads) via a ``threading.Lock``;
    ``run_inline`` keeps sync hooks on the event-loop thread for async runs.
    """

    run_inline = True
    raise_error = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Turn start: the handler is built by the owner before the run begins, so
        # this is the turn's own wall-clock origin. ``close_if_open`` uses it when
        # a failure path never reached the owner's explicit ``close(started)``.
        self._created = time.monotonic()
        # counters
        self.llm_calls = 0
        self.llm_errors = 0
        self.latency_ms: int | None = None
        self.cost_usd: float | None = None
        # aggregation state
        self._usage: dict[str, Any] = {}  # model -> UsageMetadata
        self._model_calls: dict[str, int] = {}  # model -> call count
        self._nodes: dict[str, dict[str, int]] = {}  # key -> {ms, runs}
        # in-flight state
        self._llm_starts: dict[UUID, float] = {}  # run_id -> monotonic start
        self._run_models: dict[UUID, str] = {}  # run_id -> model (from start)
        # run_id -> (key, checkpoint_ns, start)
        self._node_starts: dict[UUID, tuple[str, str, float]] = {}
        self._seen_ns: set[str] = set()  # deduped checkpoint namespaces

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
            with self._lock:
                self._llm_starts[run_id] = time.monotonic()
                name = (metadata or {}).get("ls_model_name")
                if name:
                    self._run_models[run_id] = name
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
                    return
                model = message.response_metadata.get("model_name") or start_model
                usage = message.usage_metadata
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
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_llm_error failed", exc_info=True)

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
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chain_start failed", exc_info=True)

    def _close_node(self, run_id: UUID) -> None:
        with self._lock:
            entry = self._node_starts.pop(run_id, None)
            if entry is None:
                return
            key, ns, started = entry
            # Release the namespace once the outermost run for this task closes.
            # Nested runs inherit the ns only while that run is in flight, so they
            # stay deduped; a genuine re-execution of the same task (a MIN-49
            # RetryPolicy retry reuses the deterministic checkpoint_ns) is timed
            # again instead of being silently dropped.
            self._seen_ns.discard(ns)
            ms = int((time.monotonic() - started) * 1000)
            slot = self._nodes.setdefault(key, {"ms": 0, "runs": 0})
            slot["ms"] += ms
            slot["runs"] += 1

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            self._close_node(run_id)
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chain_end failed", exc_info=True)

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            self._close_node(run_id)
        except Exception:  # pragma: no cover - defensive
            logger.debug("TurnMetricsHandler.on_chain_error failed", exc_info=True)

    # -- lifecycle / output ----------------------------------------------

    def close(self, started: float) -> None:
        """Set turn wall-clock ``latency_ms`` from an owner-held ``time.monotonic()``."""
        self.latency_ms = int((time.monotonic() - started) * 1000)

    def close_if_open(self) -> None:
        """Close the turn from the handler's own creation time if not closed yet.

        The success path closes explicitly via ``close(started)``. A failed or
        cancelled turn never reaches that call, so the finalizer uses this to
        record a real wall-clock instead of leaving ``latency_ms`` NULL (which
        would silently drop every failed turn out of the latency rollups).
        """
        if self.latency_ms is None:
            self.latency_ms = int((time.monotonic() - self._created) * 1000)

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
