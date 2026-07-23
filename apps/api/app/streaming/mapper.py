"""Map a LangGraph ``astream`` into the typed agent SSE taxonomy.

Consumes ``stream_mode=["messages", "updates"]`` with ``subgraphs=True``. On
langgraph 1.2.x (v1 emission) each item is a ``(namespace, mode, data)`` tuple:

* ``messages`` → ``data = (message_chunk, metadata)`` — token deltas. Only the
  sub-agent assistant's natural-language reply is user-facing, so we filter on
  the namespace root (the sub-agent name) and on ``AIMessage`` to suppress
  supervisor/summarizer/reflection chatter and raw ToolNode JSON.
* ``updates`` → ``data = {node_name: state_delta}`` — completed messages per
  node. Tool calls / results are read **here** (the ``messages`` chunks carry
  only partial tool-call fragments).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.constants import AGENT_ERROR_FALLBACK_MSG
from app.agents.suggestions import profile_for_suggestions, suggestions_for_flow
from app.agents.supervisor import SUBAGENTS
from app.core.streaming import TypedSSEEvent
from app.streaming import events
from app.streaming.panel_localizer import localize_panel

logger = logging.getLogger(__name__)

#: System instruction for the panel-prose translator. Kept minimal and imperative
#: so the model translates the place description into Vietnamese rather than
#: answering or echoing it, while leaving proper nouns intact.
_TRANSLATE_SYSTEM = SystemMessage(
    content=(
        "You are a translator. Translate the user's text into Vietnamese. "
        "Keep proper nouns (place names, brands, cities, landmarks) unchanged. "
        "Return ONLY the translated text — no preamble, quotes, or explanation."
    )
)

#: Main-graph nodes that end a turn with a content-bearing AIMessage (tier gate,
#: unknown intent, plan cancel/approve). Their message never streams via the
#: ``messages`` mode (only sub-agent prose does), so the mapper surfaces it from
#: the ``updates`` branch — gated on this node-name set so sub-agent content is
#: never double-emitted.
_TERMINAL_TEXT_NODES: frozenset[str] = frozenset({"supervisor", "plan"})

#: Main-graph node whose update signals a reflection-rejected draft. `reset` means
#: exactly that (drop the superseded draft) — see gh-109: keying it off assistant
#: message-id inequality instead also fired on ordinary ReAct rounds
#: (assistant prose + tool call → tool → final assistant message), making a normal
#: clarification reply visibly restart. The revision is recognised by the
#: ``revisions`` counter this node bumps when the critic says REVISE.
_REFLECTION_NODE = "reflection"


def _ns_root(ns: tuple[str, ...] | None) -> str | None:
    """Sub-agent name owning this stream item, or ``None`` at the top level.

    :param ns: The stream item's namespace tuple.
    :return: The owning sub-agent name, or ``None`` at the top level.
    """
    if not ns:
        return None
    return ns[0].split(":", 1)[0]


def _as_message_list(value: Any) -> list[Any]:
    """Coerce a node's ``messages`` update to a list (it may be a single msg).

    :param value: The ``messages`` update value.
    :return: The value coerced to a list.
    """
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
) -> AsyncIterator[TypedSSEEvent]:
    """Yield typed SSE events for one agent turn (or interrupt resume).

    ``context`` is the per-run ``AgentContext`` (mode/tier capabilities), forwarded
    to ``astream`` so streaming nodes see the same context as the buffered path.

    :param graph: The compiled LangGraph graph to stream from.
    :param stream_input: The input passed to ``graph.astream``.
    :param cfg: The run's LangGraph config (thread id, etc.).
    :param conversation_id: The conversation this turn belongs to.
    :param context: The per-run ``AgentContext``, forwarded to ``astream``.
    :param final_state_sink: When provided, populated with the post-drain
        ``values``/``interrupt_pending`` snapshot so a caller (e.g. a response
        background task) can run memory extraction after the stream completes.
    """
    yield events.start(conversation_id)

    # Seed the language BEFORE the astream loop so a HITL-resume turn (which
    # skips the supervisor and never emits a language delta) still tags its
    # panels/done with the persisted language. Best-effort — default en.
    current_language = "en"
    try:
        _pre = await graph.aget_state(cfg)
        pre_lang = _pre.values.get("language") if _pre and _pre.values else None
        if isinstance(pre_lang, str) and pre_lang:
            current_language = pre_lang
    except Exception:  # noqa: BLE001 — best-effort seed; default en
        pass

    # Translator closure for free-form panel prose; only invoked by
    # localize_panel under vi. Async end-to-end so the SSE event loop is never
    # blocked. Never call get_fast_llm() here.
    _tl = getattr(graph, "translate_llm", None)
    if _tl is not None:

        async def _translate(text: str) -> str:
            resp = await _tl.ainvoke([_TRANSLATE_SYSTEM, HumanMessage(content=text)])
            return resp.content

        translator = _translate
    else:
        translator = None

    current_subagent: str | None = None
    pending_reset: bool = False
    emitted_tool_calls: set[str] = set()
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

    try:
        async for ns, mode, data in graph.astream(
            stream_input,
            cfg,
            context=context,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            root = _ns_root(ns)

            # Announce a specialist handoff the moment its namespace appears.
            if root in SUBAGENTS and root != current_subagent:
                current_subagent = root
                yield events.subagent(root)

            if mode == "messages":
                # Only sub-agent assistant prose is user-facing. ToolNode output
                # runs in the same subgraph, so the AIMessage guard keeps raw
                # JSON out of the feed; AIMessageChunk subclasses AIMessage.
                if root not in SUBAGENTS:
                    continue
                chunk, _meta = data
                if not isinstance(chunk, AIMessage):
                    continue
                content = getattr(chunk, "content", "")
                if not content:
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
                    # Cross-cutting terminal nodes (supervisor/plan) in the main
                    # graph end the turn with a content-bearing AIMessage (tier
                    # gate, unknown intent, plan cancel/approve). That message
                    # never streams via the "messages" mode (only sub-agent prose
                    # does), so surface it here as a token — gated on the
                    # node-name key so sub-agent content (whose internal nodes are
                    # "agent"/"tools") is never double-emitted.
                    is_terminal_text_node = (
                        node_name in _TERMINAL_TEXT_NODES and not subagent_name
                    )
                    for msg in _as_message_list(delta.get("messages")):
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
                            # Panel-capable tools (response_format=content_and_artifact)
                            # carry a {"kind","data"} artifact for the side-panel drawer;
                            # surface it before the status pill. Plain tools have none.
                            artifact = getattr(msg, "artifact", None)
                            if isinstance(artifact, dict) and "kind" in artifact:
                                panel_data = await localize_panel(
                                    artifact["kind"],
                                    artifact.get("data"),
                                    current_language,
                                    translator=translator,
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
                            # Terminal supervisor/plan message — emit it as a
                            # token so gated/unknown-intent/plan turns show their
                            # explanation instead of a blank chat bubble.
                            content = getattr(msg, "content", "")
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
            )
        )
        yield events.done(
            conversation_id=conversation_id,
            current_flow=current_flow,
            suggestions=suggestions,
            language=current_language,
            trip_id=state.values.get("trip_id") if state else None,
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
        # Always return a readable message to the user, even when the run failed
        # before the assistant produced any reply (tool outage, LLM error, or a
        # ReAct loop that exhausted the recursion limit on repeated tool errors).
        # Emit a friendly fallback token so the chat bubble is never empty and the
        # turn is persisted; the terminal error event still signals the failure
        # downstream (e.g. the FE retry affordance).
        if not emitted_token:
            yield events.token(AGENT_ERROR_FALLBACK_MSG)
        yield events.error(code="internal", message=str(exc))
