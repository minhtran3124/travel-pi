"""AgentRunner port impl for travel-pi: drives the compiled LangGraph travel
agent for one golden and captures a fully-populated Trace.

Ports the graph-invocation logic of the legacy `eval/harness.py` (build the
graph, invoke with a thread_id, extract the final AIMessage / current_flow)
and extends it in two ways task 2.2/2.3/3.2 depend on:

- every ToolMessage output is paired back onto its AIMessage tool_call by
  `tool_call_id` (never by position — a ReAct round-trip can interleave
  multiple calls) so `Trace.tool_calls[].output` carries real tool results;
- the full ordered message list is serialized to plain dicts (`Trace.messages`)
  for the trajectory metric, without leaking any langchain object into
  evalkit (which must stay framework-free per design-portability.md).

Known gotcha (agent memory `eval-harness-bypasses-db-config-and-context`):
invoking the graph directly bypasses the request-scoped `AgentConfigCache`.
When no `llm`/`fast_llm` override is injected, every node falls back to
`get_agent_llm`'s env-configured model (`gpt-5`/`gpt-5-mini`) and needs a
real provider key at call time — otherwise a 403. This is NOT fixed here;
tests always inject `FakeLLM` so they stay network-free.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from app.agents.context import AgentContext
from app.agents.suggestions import suggestions_for_flow
from app.memory.extraction_runner import run_memory_extraction
from evalkit.types import Golden, Trace
from evalkit.types import ToolCall as EvalToolCall
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


def build_eval_graph(
    *, llm: BaseChatModel | None = None, fast_llm: BaseChatModel | None = None
) -> Any:
    """Build the travel graph for eval (ported from the legacy `eval/harness.py`).

    Uses an in-memory checkpointer/store — eval is single-shot per golden run,
    no cross-process persistence needed.

    :param llm: Override chat model for main-tier nodes (tests inject FakeLLM).
    :param fast_llm: Override chat model for fast-tier nodes (tests inject FakeLLM).
    :return: The compiled travel agent graph.
    """
    from app.agents.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    return build_graph(
        llm=llm, fast_llm=fast_llm, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _final_reply(messages: list[BaseMessage]) -> str:
    """The last AIMessage's text content, flattening provider content blocks."""
    ai = [m for m in messages if isinstance(m, AIMessage)]
    if not ai:
        return ""
    content = ai[-1].content
    if isinstance(content, str):
        return content
    # Provider block-list content (Anthropic/Bedrock): concatenate text blocks.
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def _raw_tool_calls(message: BaseMessage) -> list[dict[str, Any]]:
    """Normalize a message's `.tool_calls` (dict or object items) to plain dicts."""
    raw = getattr(message, "tool_calls", None) or []
    calls: list[dict[str, Any]] = []
    for tc in raw:
        if isinstance(tc, dict):
            calls.append(tc)
        else:
            calls.append(
                {
                    "name": getattr(tc, "name", None),
                    "args": getattr(tc, "args", None),
                    "id": getattr(tc, "id", None),
                }
            )
    return calls


def _pair_tool_calls(messages: list[BaseMessage]) -> list[EvalToolCall]:
    """Pair each AIMessage tool_call with its ToolMessage result by `tool_call_id`.

    Pairing by id (not position) matters: a ReAct loop can interleave several
    tool calls per round-trip, and message ordering doesn't guarantee they
    line up positionally with their results.
    """
    outputs_by_id: dict[str, Any] = {
        m.tool_call_id: m.content for m in messages if isinstance(m, ToolMessage)
    }
    calls: list[EvalToolCall] = []
    for m in messages:
        for tc in _raw_tool_calls(m):
            name = tc.get("name")
            if not name:
                continue
            calls.append(
                EvalToolCall(
                    name=name,
                    args=tc.get("args") or {},
                    output=outputs_by_id.get(tc.get("id")),
                )
            )
    return calls


def _serialize_message(m: BaseMessage) -> dict[str, Any]:
    """One langchain message -> a framework-free dict for `Trace.messages`."""
    content = m.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    out: dict[str, Any] = {"type": m.type, "content": content}
    tool_calls = _raw_tool_calls(m)
    if tool_calls:
        out["tool_calls"] = tool_calls
    tool_call_id = getattr(m, "tool_call_id", None)
    if tool_call_id:
        out["tool_call_id"] = tool_call_id
    name = getattr(m, "name", None)
    if name:
        out["name"] = name
    return out


def _model_name(model: BaseChatModel | None) -> str | None:
    """Best-effort model identifier for `Trace.meta` (varies across providers)."""
    if model is None:
        return None
    return (
        getattr(model, "model", None)
        or getattr(model, "model_name", None)
        or type(model).__name__
    )


# Metrics whose golden fields the memory-capture path feeds. Extraction runs an
# extra LLM call and writes to the store, so capture is opt-in: only a golden
# declaring one of these metrics pays for it (design §5, SC-9). A golden that
# sets `forbidden_memory`/`expected_memory` without naming the metric is inert —
# guarded by a dataset test, the false-green trap one layer out.
_MEMORY_METRICS = frozenset({"no_injected_memory", "memory_stored"})

# Store namespace kind -> the flat `kind` label emitted on Trace.meta["memory"].
_MEMORY_KINDS: dict[str, str] = {
    "prefs": "preferences",
    "procedural": "instructions",
    "episodes": "episodes",
}


def _wants_memory_capture(golden: Golden) -> bool:
    """True when *golden* declares a metric that reads ``Trace.meta['memory']``."""
    return bool(_MEMORY_METRICS.intersection(golden.metrics or ()))


def _eval_user_id(golden_id: str) -> str:
    """Per-golden store user id so one golden's captured memory never leaks to another.

    The eval CLI builds ONE ``LangGraphRunner`` (one ``build_eval_graph`` → one
    ``InMemoryStore``) for the whole run and drives every golden through it. If
    every golden wrote under a single fixed user id, ``_capture_memory`` would
    persist into a namespace ``load_context_node`` then re-reads for every LATER
    golden — the positive golden's stored "always show prices in EUR" would stand
    as a standing instruction in every subsequent system prompt (shifting results
    and the ``eval-check`` baseline), and within the memory goldens a negative
    could be reddened, or a positive pass, on an item another golden wrote.

    Deriving the id from the golden's unique, stable id gives each golden its own
    ``("users", "eval-<id>", …)`` subtree. Deterministic (no uuid): the same
    golden always reads back exactly and only what it wrote.

    :param golden_id: The golden's dataset id.
    :return: A user id unique to that golden.
    """
    return f"eval-{golden_id}"


def _stored_memory(store: Any, user_id: str) -> list[dict[str, Any]]:
    """Snapshot every memory item persisted for *user_id*, flattened for the metrics.

    Reads the store namespaces directly rather than through the read-guard
    helpers: the memory metrics gate on what the write path actually PERSISTED,
    so a poisoned item the write guard dropped must be genuinely absent here (not
    merely hidden by a read-side filter). Each item is emitted with a flat
    ``text`` key — ``no_injected_memory`` reads ``item["text"]`` and
    ``memory_stored`` reads ``item["key"]`` (design §5).

    :param store: The compiled graph's LangGraph store.
    :param user_id: Owning user id the eval turn wrote under.
    :return: ``{"kind", "key", "text"}`` dicts across all three memory kinds.
    """
    items: list[dict[str, Any]] = []
    for ns_kind, label in _MEMORY_KINDS.items():
        for it in store.search(("users", user_id, ns_kind), limit=100):
            value = it.value if isinstance(it.value, dict) else {}
            items.append({"kind": label, "key": it.key, "text": value.get("text")})
    return items


class LangGraphRunner:
    """`AgentRunner` port impl: drives the compiled travel graph for one golden.

    Multi-turn goldens (`golden.turns`) replay sequentially on ONE thread_id
    so the checkpointer accumulates state across turns like a real
    conversation. Each `run()` call mints its OWN fresh, unique thread_id —
    reusing a thread_id across different goldens would poison state (bleed
    prior turns into an unrelated case), the mirror-image gotcha to the
    intra-golden replay this class deliberately does.
    """

    def __init__(
        self,
        *,
        llm: BaseChatModel | None = None,
        fast_llm: BaseChatModel | None = None,
        graph: Any | None = None,
        context: AgentContext | None = None,
    ) -> None:
        """
        :param llm: Override chat model for main-tier nodes (tests inject FakeLLM);
            ignored when `graph` is supplied directly.
        :param fast_llm: Override chat model for fast-tier nodes.
        :param graph: A pre-built compiled graph; takes precedence over `llm`/`fast_llm`.
        :param context: Per-run `AgentContext`; defaults to the fixed BALANCED set.
        """
        self._model = _model_name(llm) or _model_name(fast_llm)
        self._graph = (
            graph if graph is not None else build_eval_graph(llm=llm, fast_llm=fast_llm)
        )
        self._context = context if context is not None else AgentContext()

    def _drive(self, payload: Any, cfg: dict[str, Any]) -> dict[str, Any]:
        """Run one graph turn asynchronously, the way production does.

        ``synthesis_worker`` is an async node (#178: the specialists bind
        async-only tools such as ``get_weather``), so a sync ``graph.invoke``
        cannot execute a fanned-out turn at all. Driving the graph with
        ``ainvoke`` also makes the eval measure the same execution mode the API
        serves — before this, every multi-intent golden was scored against the
        sync path, where an async tool took its whole batch down and the
        specialist reported a false outage.

        ``asyncio.run`` is safe here and not in the graph itself: the eval CLI is
        a batch entry point with no enclosing event loop.

        :param payload: The turn input (initial state dict, or a ``Command``).
        :param cfg: The LangGraph config carrying this golden's thread id.
        :return: The graph's output state for this turn.
        """
        return asyncio.run(self._graph.ainvoke(payload, cfg, context=self._context))

    def _capture_memory(
        self, out: dict[str, Any], user_id: str
    ) -> list[dict[str, Any]]:
        """Run post-turn extraction against the eval graph's store, then snapshot it.

        Mirrors production: ``run_memory_extraction`` writes through the same
        store write-guard the API uses (``compiled.store``) with the graph's own
        ``extract_memory_llm`` (``graph.py:200``), so what lands on
        ``Trace.meta['memory']`` is exactly what a real turn would persist — a
        poisoned item the guard rejects is absent. Best-effort: extraction already
        swallows its own errors, and a graph missing the store/LLM seam yields an
        empty snapshot.

        The snapshot is read back from *user_id*'s own namespace (§Finding 1): the
        shared eval store is written and read per golden, so nothing another golden
        stored is visible here.

        The vacuity trap — an empty snapshot from a rejected poison looking
        identical to one where nothing was extracted at all — is closed by the
        adversarial goldens themselves: each carries a legitimate preference
        alongside the injection, so a healthy run stores that preference and an
        empty snapshot is itself the anomaly signal.

        :param out: The final graph state for this golden's last turn.
        :param user_id: This golden's isolated store user id.
        :return: The flattened stored-memory items.
        """
        store = getattr(self._graph, "store", None)
        llm = getattr(self._graph, "extract_memory_llm", None)
        if store is None or llm is None:
            return []
        messages = out.get("messages", [])
        run_memory_extraction(
            messages=messages,
            user_id=user_id,
            trip_id=out.get("trip_id"),
            plan_approved=out.get("plan_approved", False),
            allow_memory_write=True,
            store=store,
            llm=llm,
        )
        return _stored_memory(store, user_id)

    def run(self, golden: Golden) -> Trace:
        """Invoke the graph for *golden* (single input or multi-turn) -> Trace."""
        thread_id = f"eval-{golden.id}-{uuid.uuid4().hex[:8]}"
        cfg = {"configurable": {"thread_id": thread_id}}
        turns = golden.turns if golden.turns is not None else [golden.input]
        # Per-golden store namespace: the runner's InMemoryStore is shared across
        # every golden in the run, so a fixed user id would leak one golden's
        # captured memory into every later golden (see _eval_user_id).
        user_id = _eval_user_id(golden.id)

        start = time.monotonic()
        out: dict[str, Any] = {}
        interrupts: list[dict[str, Any]] = []
        for i, turn in enumerate(turns):
            payload: dict[str, Any] = {"messages": [HumanMessage(content=turn)]}
            if i == 0:
                # Only the first turn on a fresh thread needs the initial state
                # shape; the checkpointer carries it forward on later turns.
                payload["user_id"] = user_id
                payload["trip_id"] = None
            out = self._drive(payload, cfg)

            pending = [
                iv.value
                for iv in out.get("__interrupt__", ())
                if isinstance(getattr(iv, "value", None), dict)
                and iv.value.get("type") == "plan_approval"
            ]
            if pending:
                # At most one resume per turn.
                interrupts.append(
                    {
                        "type": pending[0]["type"],
                        "draft": pending[0]["draft"],
                        "turn": i,
                    }
                )
                hitl = getattr(golden, "hitl", None)
                if hitl is not None:
                    out = self._drive(
                        Command(resume={"approved": hitl == "approve"}), cfg
                    )
        elapsed = time.monotonic() - start

        messages = out.get("messages", [])
        meta: dict[str, Any] = {
            "thread_id": thread_id,
            "model": self._model,
            "elapsed_s": elapsed,
            "n_turns": len(turns),
            "tasks": [t.get("agent") for t in out.get("tasks") or []],
            "suggestions": suggestions_for_flow(
                out.get("current_flow"), trip_facts=out.get("trip_facts")
            ),
            "interrupts": interrupts,
        }
        # Opt-in: only goldens that declare a memory metric pay for the extra
        # extraction call. The key must be PRESENT (even as []) for those goldens
        # — the metrics treat a missing "memory" key as a hard fail (extraction
        # never ran), so absence is never a silent pass.
        if _wants_memory_capture(golden):
            meta["memory"] = self._capture_memory(out, user_id)
        return Trace(
            reply=_final_reply(messages),
            tool_calls=_pair_tool_calls(messages),
            flow=out.get("current_flow"),
            messages=[_serialize_message(m) for m in messages],
            meta=meta,
        )
