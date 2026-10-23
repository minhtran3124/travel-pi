"""Map a LangGraph ``astream`` into the typed agent SSE taxonomy.

``messages`` mode carries token deltas (filtered to user-facing sub-agent prose);
``updates`` mode carries completed messages, where tool calls/results are read
since the ``messages`` chunks only carry partial tool-call fragments.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.copy import system_reply
from app.agents.suggestions import profile_for_suggestions, suggestions_for_flow
from app.agents.supervisor import SUBAGENTS
from app.core.languages import DEFAULT_LANGUAGE
from app.core.pricing import estimate_cost
from app.core.streaming import TypedSSEEvent
from app.streaming import events
from app.streaming.panel_localizer import localize_panel

if TYPE_CHECKING:
    from app.agents.metrics import TurnMetricsHandler

logger = logging.getLogger(__name__)

#: Main-graph nodes whose terminal AIMessage never streams via ``messages`` mode,
#: so the mapper surfaces it from ``updates`` gated on this set to avoid double-emit.
_TERMINAL_TEXT_NODES: frozenset[str] = frozenset({"supervisor", "plan", "research"})

#: Main-graph node whose update signals a reflection-rejected draft. `reset` means
#: exactly that (drop the superseded draft) — see gh-109: keying it off assistant
#: message-id inequality instead also fired on ordinary ReAct rounds
#: (assistant prose + tool call → tool → final assistant message), making a normal
#: clarification reply visibly restart. The revision is recognised by the
#: ``revisions`` counter this node bumps when the critic says REVISE.
_REFLECTION_NODE = "reflection"


def _chunk_text(chunk: Any) -> str:
    """Return only the user-visible text of a message or chunk.

    Anthropic streams ``content`` as a list of ``thinking`` / ``text`` /
    ``tool_use`` blocks; ``.text`` keeps the text blocks and drops the rest.
    Plain-string content passes through unchanged.
    """
    return getattr(chunk, "text", "") or ""


def _ns_root(ns: tuple[str, ...] | None) -> str | None:
    """Sub-agent name owning this stream item, or ``None`` at the top level."""
    if not ns:
        return None
    return ns[0].split(":", 1)[0]


def _node_name_from_meta(meta: dict) -> str | None:
    """Return the LangGraph node name from message metadata, if present."""
    return meta.get("langgraph_node") if isinstance(meta, dict) else None


def _as_message_list(value: Any) -> list[Any]:
    """Coerce a node's ``messages`` update to a list (it may be a single msg)."""
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


async def stream_agent_events(
    graph: Any,
    stream_input: Any,
    *,
    cfg: dict,
    conversation_id: str,
    context: Any = None,
    final_state_sink: dict | None = None,
    metrics: TurnMetricsHandler | None = None,
) -> AsyncIterator[TypedSSEEvent]:
    """Yield typed SSE events for one agent turn (or interrupt resume).

    ``final_state_sink``, when provided, is populated with the post-drain
    ``values``/``interrupt_pending`` snapshot for post-stream memory extraction.
    """
    started = time.monotonic()
    yield events.start(conversation_id)

    # Seed the language BEFORE the astream loop so a HITL-resume turn (which
    # skips the supervisor and never emits a language delta) still tags its
    # panels/done with the persisted language.
    current_language = DEFAULT_LANGUAGE
    # A sub-agent shares the parent's state schema, so the parent-level update
    # carries the thread's WHOLE messages list; without these prior ids every
    # past turn's tool calls/results would re-emit on every turn.
    prior_msg_ids: set[str] = set()
    prior_tool_call_ids: set[str] = set()
    try:
        _pre = await graph.aget_state(cfg)
        pre_lang = _pre.values.get("language") if _pre and _pre.values else None
        if isinstance(pre_lang, str) and pre_lang:
            current_language = pre_lang
        for m in _as_message_list((_pre.values or {}).get("messages")) if _pre else []:
            mid = getattr(m, "id", None)
            if isinstance(mid, str) and mid:
                prior_msg_ids.add(mid)
            for tc in getattr(m, "tool_calls", None) or []:
                if tc.get("id"):
                    prior_tool_call_ids.add(tc["id"])
    except Exception:  # noqa: BLE001 — best-effort seed; default en
        pass

    current_subagent: str | None = None
    pending_reset: bool = False
    emitted_tool_calls: set[str] = set(prior_tool_call_ids)
    # The same ToolMessage is seen twice per turn (subgraph tools node + parent
    # sub-agent node); emit its panel/result once.
    emitted_tool_results: set[str] = set(prior_tool_call_ids)
    emitted_token: bool = False
    # gh-109: an assistant message may carry prose AND tool calls. That prose is a
    # preamble the model repeats in the post-tool answer, so streaming it live
    # duplicates the reply. Hold each assistant message's prose until its completed
    # `updates` entry says whether it called tools: drop it if it did, flush it if
    # it didn't.
    buffered_msg_id: str | None = None
    buffered_text: list[str] = []
    #: Sub-agent whose answer is currently on screen, so a different sub-agent's
    #: answer can supersede it (see the flush branch below).
    last_answer_subagent: str | None = None
    # Dedupe the synthesize answer by message id, not by "first event";
    # ``synthesize_seen`` distinguishes "no chunk yet" from a chunk whose id is
    # None, so a provider that omits ids still streams the whole answer.
    synthesize_seen: bool = False
    synthesize_msg_id: str | None = None

    try:
        async for ns, mode, data in graph.astream(
            stream_input,
            cfg,
            context=context,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            root = _ns_root(ns)

            if root in SUBAGENTS and root != current_subagent:
                # A superseding answer emits its own lazy `reset` (see the flush
                # branch below), so a specialist that produces no prose never
                # blanks the bubble.
                current_subagent = root
                yield events.subagent(root)

            if mode == "messages":
                chunk, meta = data
                if not isinstance(chunk, AIMessage):
                    continue
                content = _chunk_text(chunk)
                if not content:
                    continue
                node_name = _node_name_from_meta(meta)
                # Top-level synthesizer is the final answer for multi-intent.
                # LangGraph emits it more than once (model stream + graph update),
                # so dedupe by message id — not by "first event only", which would
                # ship a one-character reply since the answer arrives chunk by
                # chunk under streaming=True.
                if root is None and node_name == "synthesize":
                    synth_msg_id = getattr(chunk, "id", None)
                    if not synthesize_seen:
                        synthesize_seen = True
                        synthesize_msg_id = synth_msg_id
                    elif synth_msg_id != synthesize_msg_id:
                        # A different message for the same node is the duplicate;
                        # further chunks of the same message are the rest of the
                        # answer and must go out.
                        continue
                    emitted_token = True
                    yield events.token(content)
                    continue
                # Suppress prose from synthesis workers and their inner sub-agents.
                if root == "synthesis_worker" or (
                    root is not None and root.startswith("synthesis_worker")
                ):
                    continue
                if root not in SUBAGENTS:
                    continue
                msg_id = getattr(chunk, "id", None)
                if msg_id != buffered_msg_id:
                    buffered_msg_id = msg_id
                    buffered_text = []
                buffered_text.append(content)

            elif mode == "updates":
                subagent_name = root if root in SUBAGENTS else None
                for node_name, delta in (data or {}).items():
                    if not isinstance(delta, dict):
                        continue
                    # Capture the language the moment a node (the supervisor)
                    # persists it, so subsequent panels/done in this turn tag it.
                    node_lang = delta.get("language")
                    if isinstance(node_lang, str) and node_lang:
                        current_language = node_lang
                    # The one legitimate `reset` trigger: reflection bumped
                    # `revisions` and routed back to the sub-agent, so everything
                    # streamed so far is a rejected draft.
                    if (
                        node_name == _REFLECTION_NODE
                        and "revisions" in delta
                        and emitted_token
                    ):
                        pending_reset = True
                    # Terminal supervisor/plan AIMessage never streams via
                    # "messages" mode, so surface it here — gated on node name so
                    # sub-agent content (nodes "agent"/"tools") is not double-emitted.
                    is_terminal_text_node = (
                        node_name in _TERMINAL_TEXT_NODES and not subagent_name
                    )
                    for msg in _as_message_list(delta.get("messages")):
                        if getattr(msg, "id", None) in prior_msg_ids:
                            continue  # thread history replayed by a subgraph update
                        if isinstance(msg, AIMessage) and msg.tool_calls:
                            # This message's streamed prose was only a preamble to
                            # the tool call — the post-tool answer restates it.
                            if getattr(msg, "id", None) == buffered_msg_id:
                                buffered_text = []
                            for tc in msg.tool_calls:
                                tc_id = tc.get("id") or ""
                                if not tc_id or tc_id in emitted_tool_calls:
                                    continue
                                emitted_tool_calls.add(tc_id)
                                yield events.tool_call(
                                    id=tc_id,
                                    name=tc.get("name", ""),
                                    args=tc.get("args", {}),
                                    subagent=subagent_name,
                                )
                        elif isinstance(msg, ToolMessage):
                            if msg.tool_call_id in emitted_tool_results:
                                continue
                            emitted_tool_results.add(msg.tool_call_id)
                            # Panel-capable tools carry a {"kind","data"} artifact
                            # for the side-panel drawer; surface it before the pill.
                            artifact = getattr(msg, "artifact", None)
                            if isinstance(artifact, dict) and "kind" in artifact:
                                panel_data = await localize_panel(
                                    artifact["kind"],
                                    artifact.get("data"),
                                    current_language,
                                )
                                yield events.panel(
                                    tool_call_id=msg.tool_call_id,
                                    kind=artifact["kind"],
                                    data=panel_data,
                                    language=current_language,
                                )
                            status = "error" if msg.status == "error" else "ok"
                            yield events.tool_result(id=msg.tool_call_id, status=status)
                        elif is_terminal_text_node and isinstance(msg, AIMessage):
                            # Emit as a token so gated/unknown-intent/plan turns
                            # show their explanation instead of a blank bubble.
                            content = _chunk_text(msg)
                            if content:
                                emitted_token = True
                                yield events.token(content)
                        elif (
                            subagent_name
                            and isinstance(msg, AIMessage)
                            and getattr(msg, "id", None) == buffered_msg_id
                            and buffered_text
                        ):
                            # A completed sub-agent message with no tool calls: the
                            # answer. Release the prose held back above.
                            if pending_reset or (
                                last_answer_subagent is not None
                                and subagent_name != last_answer_subagent
                            ):
                                # Two supersede cases, both meaning "drop what is
                                # already on screen":
                                #   - reflection rejected the previous draft;
                                #   - a *different* sub-agent just answered. Each
                                #     queued ledger step regenerates a COMPLETE
                                #     answer rather than contributing a slice, so
                                #     draining a 4-step ledger otherwise shows the
                                #     same reply four times (gh-109). Only the last
                                #     sub-agent's answer is the turn's answer.
                                # Emitted lazily, just before the superseding text,
                                # so a step that produces no prose never blanks the
                                # bubble. NOT keyed to message-id inequality — that
                                # also fires inside one sub-agent's ReAct round and
                                # made a single reply visibly restart.
                                pending_reset = False
                                yield events.reset()
                            last_answer_subagent = subagent_name
                            emitted_token = True
                            yield events.token("".join(buffered_text))
                            buffered_text = []

        # Safety net: a sub-agent message whose completing `updates` entry never
        # arrived is still the traveller's answer — never swallow it.
        if buffered_text:
            if pending_reset:
                pending_reset = False
                yield events.reset()
            emitted_token = True
            yield events.token("".join(buffered_text))
            buffered_text = []

        # Pending HITL interrupt is on the snapshot, not in the stream.
        state = await graph.aget_state(cfg)
        interrupts = state.interrupts
        if final_state_sink is not None:
            final_state_sink["values"] = state.values if state else {}
            final_state_sink["interrupt_pending"] = bool(interrupts)
        if interrupts:
            logger.debug(
                "[stream_agent_events] interrupt pending for conv=%s", conversation_id
            )
            yield events.interrupt(
                conversation_id=conversation_id, payload=interrupts[0].value
            )

        current_flow = state.values.get("current_flow") if state else None
        suggestions = (
            []
            if interrupts
            else suggestions_for_flow(
                current_flow,
                trip_facts=state.values.get("trip_facts") if state else None,
                profile=profile_for_suggestions(
                    getattr(graph, "store", None),
                    state.values.get("user_id") if state else None,
                ),
                preferences=(state.values.get("preferences", "") if state else ""),
                # ``None`` (premium) keeps every specialist reachable; a missing
                # context falls back to "no premium specialist", never all-allowed.
                allowed_subagents=getattr(context, "allowed_subagents", frozenset()),
            )
        )
        usage = None
        if metrics is not None:
            # Guarded: this block is inside the stream's try, so an exception
            # here would turn a successful `done` into an `error`.
            try:
                metrics.close(started)
                snap = metrics.snapshot()
                metrics.cost_usd = estimate_cost(snap["by_model"])
                usage = metrics.public()
            except Exception:  # noqa: BLE001 — best-effort metrics
                logger.debug(
                    "[stream_agent_events] metrics finalize failed", exc_info=True
                )
        yield events.done(
            conversation_id=conversation_id,
            current_flow=current_flow,
            suggestions=suggestions,
            language=current_language,
            trip_id=state.values.get("trip_id") if state else None,
            usage=usage,
        )

    except Exception as exc:  # noqa: BLE001 — surface failure as a terminal event
        import asyncio

        # The run died before the message that was streaming could complete. Its
        # prose is still the only answer the traveller has — release it rather
        # than dropping it (and replacing it with the generic fallback below).
        if buffered_text:
            emitted_token = True
            yield events.token("".join(buffered_text))
            buffered_text = []

        if isinstance(exc, asyncio.CancelledError):
            yield events.error(code="cancelled", message="Stream cancelled")
            raise
        logger.exception(
            "[stream_agent_events] stream failed for conv=%s", conversation_id
        )
        # Emit a fallback token when the run failed before any reply, so the chat
        # bubble is never empty and the turn is persisted; the error event still
        # signals failure downstream.
        if not emitted_token:
            yield events.token(
                await asyncio.to_thread(
                    system_reply, "agent_error_fallback", current_language
                )
            )
        yield events.error(code="internal", message=str(exc))
