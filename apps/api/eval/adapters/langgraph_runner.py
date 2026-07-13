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

import logging
import time
import uuid
from typing import Any

from app.agents.context import AgentContext
from evalkit.types import Golden, Trace
from evalkit.types import ToolCall as EvalToolCall
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

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

    def run(self, golden: Golden) -> Trace:
        """Invoke the graph for *golden* (single input or multi-turn) -> Trace."""
        thread_id = f"eval-{golden.id}-{uuid.uuid4().hex[:8]}"
        cfg = {"configurable": {"thread_id": thread_id}}
        turns = golden.turns if golden.turns is not None else [golden.input]

        start = time.monotonic()
        out: dict[str, Any] = {}
        for i, turn in enumerate(turns):
            payload: dict[str, Any] = {"messages": [HumanMessage(content=turn)]}
            if i == 0:
                # Only the first turn on a fresh thread needs the initial state
                # shape; the checkpointer carries it forward on later turns.
                payload["user_id"] = "eval"
                payload["trip_id"] = None
            out = self._graph.invoke(payload, cfg, context=self._context)
        elapsed = time.monotonic() - start

        messages = out.get("messages", [])
        return Trace(
            reply=_final_reply(messages),
            tool_calls=_pair_tool_calls(messages),
            flow=out.get("current_flow"),
            messages=[_serialize_message(m) for m in messages],
            meta={
                "thread_id": thread_id,
                "model": self._model,
                "elapsed_s": elapsed,
                "n_turns": len(turns),
            },
        )
