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

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.constants import AGENT_ERROR_FALLBACK_MSG
from app.agents.supervisor import SUBAGENTS
from app.core.streaming import TypedSSEEvent
from app.streaming import events

logger = logging.getLogger(__name__)


def _ns_root(ns: tuple[str, ...] | None) -> str | None:
    """Sub-agent name owning this stream item, or ``None`` at the top level."""
    if not ns:
        return None
    return ns[0].split(":", 1)[0]


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
) -> AsyncIterator[TypedSSEEvent]:
    """Yield typed SSE events for one agent turn (or interrupt resume).

    ``context`` is the per-run ``AgentContext`` (mode/tier capabilities), forwarded
    to ``astream`` so streaming nodes see the same context as the buffered path.
    """
    yield events.start(conversation_id)

    current_subagent: str | None = None
    last_msg_id: str | None = None
    emitted_tool_calls: set[str] = set()
    emitted_token: bool = False

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
                if (
                    last_msg_id is not None
                    and msg_id is not None
                    and msg_id != last_msg_id
                ):
                    # A new assistant message started (reflection revision) —
                    # tell the client to drop the superseded draft.
                    yield events.reset()
                last_msg_id = msg_id
                emitted_token = True
                yield events.token(content)

            elif mode == "updates":
                subagent_name = root if root in SUBAGENTS else None
                for delta in (data or {}).values():
                    if not isinstance(delta, dict):
                        continue
                    for msg in _as_message_list(delta.get("messages")):
                        if isinstance(msg, AIMessage) and msg.tool_calls:
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
                                yield events.panel(
                                    tool_call_id=msg.tool_call_id,
                                    kind=artifact["kind"],
                                    data=artifact.get("data"),
                                )
                            status = "error" if msg.status == "error" else "ok"
                            yield events.tool_result(id=msg.tool_call_id, status=status)

        # Pending HITL interrupt is on the snapshot, not in the stream.
        state = await graph.aget_state(cfg)
        interrupts = state.interrupts
        if interrupts:
            logger.debug(
                "[stream_agent_events] interrupt pending for conv=%s", conversation_id
            )
            yield events.interrupt(
                conversation_id=conversation_id, payload=interrupts[0].value
            )

        current_flow = state.values.get("current_flow") if state else None
        yield events.done(conversation_id=conversation_id, current_flow=current_flow)

    except Exception as exc:  # noqa: BLE001 — surface failure as a terminal event
        import asyncio

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
