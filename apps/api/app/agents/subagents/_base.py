"""Sub-agent factory: a specialist is a small ReAct subgraph (assistant + ToolNode).

Compiled subgraphs are added as nodes to the supervisor graph; the parent's
checkpointer and store propagate in, so ``InjectedStore`` tools need no wiring.
"""

from __future__ import annotations

import logging
import typing
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agents.constants import EPISODIC_TOOL_NAME, NO_ACTIVE_TRIP_MSG
from app.agents.context import AgentContext
from app.agents.retry import LLM_RETRY, ToolFaultPolicy, describe_tool_failure
from app.agents.state import (
    TravelAgentState,
    demote_midstream_system,
    ground_current_date,
    provider_of,
    strip_foreign_reasoning,
    system_with_summary,
    with_reply_language,
    with_task_note,
)
from app.agents.tool_output import TAG_NAME, wrap_tool_output
from app.prompts.registry import registry
from app.tools.clarification_tools import needs_clarification

logger = logging.getLogger(__name__)


def _tool_error_to_message(exc: Exception) -> str:
    """Render any tool failure as a ``ToolMessage`` the model can relay, instead
    of letting it crash the run.

    langgraph's default handler only catches arg-validation
    (``ToolInvocationError``) and re-raises everything else — so the
    ``ToolException`` our tools raise on an upstream outage (e.g. Open-Meteo
    timing out) would otherwise propagate out of ``astream`` and 500 the whole
    ``/agent/stream`` request. Annotating ``exc: Exception`` tells ToolNode's
    ``_infer_handled_types`` to catch every tool error.

    Breadth is deliberate; the *verdict* is not. This used to label every caught
    failure "a temporary upstream problem … try again shortly", so a
    deterministic failure was narrated to the traveller as an outage with advice
    that could never work (#113). The wording now comes from
    :func:`app.agents.retry.describe_tool_failure`, shared with the
    ``ToolFaultPolicy`` hook so both paths give one answer per failure class.

    :param exc: The exception raised by a tool call.
    :return: A user-safe message describing the failure.
    """
    return describe_tool_failure(exc)


#: A wrapped block begins with this fixed prefix. The opening tag carries a
#: variable ``name`` attribute, so there is no full literal tag to match — the
#: leading token is enough to recognise already-wrapped content and skip it, which
#: is what keeps the node idempotent across a checkpoint resume.
_WRAPPED_PREFIX = f"<{TAG_NAME} "


def _label_one(msg: ToolMessage) -> ToolMessage:
    """Escape and wrap one tool message, or return it unchanged when a skip rule
    applies (specs/rag-tool-output-wrapping, Task 2.1, design §4).

    The wrapped copy is built with ``model_copy`` so ``id`` (and every other
    field — ``tool_call_id``, ``name``, ``status``, ``artifact``) is preserved:
    the ``add_messages`` reducer upserts by ``id``, so a same-``id`` copy replaces
    the message in place, while a fresh ``ToolMessage`` would regenerate ``id`` and
    silently duplicate every tool result in the transcript.

    Left untouched (the same object is returned): ``status == "error"``
    (first-party recovery text, D3); non-``str`` content (logged at debug); empty
    content; and content already wrapped (the wrapper is re-entrant across a
    checkpoint resume and wrapping does not compose). A transform that raises
    delivers that one message unchanged and logs a warning — never dropped, since
    an unanswered ``tool_call_id`` makes the provider reject the next assistant
    turn.

    :param msg: A ``ToolMessage`` produced by the ``tools`` node.
    :return: A same-``id`` wrapped copy, or ``msg`` itself when a skip rule holds.
    """
    if msg.status == "error":
        return msg
    content = msg.content
    if not isinstance(content, str):
        logger.debug(
            "[agent] tool_output: non-str content from tool %r — left unwrapped",
            msg.name,
        )
        return msg
    if not content:
        return msg
    if content.startswith(_WRAPPED_PREFIX):
        return msg
    try:
        wrapped = wrap_tool_output(msg.name or "", content)
    except Exception:
        # Never drop a ToolMessage: a missing tool_call_id makes the provider
        # reject the next assistant turn. Deliver the original and warn.
        logger.warning(
            "[agent] tool_output: wrapping failed for tool %r — delivering "
            "the message unchanged",
            msg.name,
            exc_info=True,
        )
        return msg
    return msg.model_copy(update={"content": wrapped})


def _label_tool_outputs(result):
    """Label the ``tools`` node's freshly-produced output as data (Task 2.1, D1/E002).

    A tool result arrives as unlabelled text in the same conversation the
    assistant's own rules live in, so a hostile payload ("ignore your previous
    instructions …") is typographically indistinguishable from an instruction.
    This post-processes the value the wrapped ``ToolNode`` returned, escaping and
    wrapping every ordinary ``ToolMessage`` in a ``<tool_output>`` block so the
    model reads it as data.

    The seam is the ``tools`` node's own callable, not langgraph's
    ``wrap_tool_call`` hook (E001) and not a node placed after ``tools`` (E002):
    the hook intercepts *during* execution and its wrapper path catches every
    exception with no handled-types gate, disarming ``TRANSIENT_RETRY`` +
    ``graceful_fallback``; a following node adds a super-step this repo already
    removed once, overrunning ``agent_recursion_limit``. Here the ``ToolNode``
    runs (or raises) exactly as before and this function only ever sees the value
    execution produced — an exception propagates past it untouched, so
    ``RetryPolicy`` / ``error_handler`` are framed identically to a bare
    ``ToolNode``.

    ``ToolNode`` returns **two distinct shapes** (confirmed against
    ``ToolNode._combine_tool_outputs``, not the declared type). When no tool call
    returned a ``Command``, the whole batch is a single ``dict`` with a
    ``"messages"`` list, every entry a ``ToolMessage``. When at least one call
    returned a ``Command``, the batch is a ``list`` whose entries are **either** a
    ``Command`` **or** a per-message ``dict`` — ``{"messages": [ToolMessage]}`` —
    because this graph always invokes the node with a state ``dict`` (so
    ``input_type == "dict"``, and ``_combine_tool_outputs`` wraps each ordinary
    output as ``{self._messages_key: [output]}``, never a bare ``ToolMessage``).
    Every ``Command`` is left untouched (D3: a first-party success ``ToolMessage``
    built inside a ``Command.update``, e.g. ``clarification_tools.py:55`` /
    ``trip_tools.py:583``, arrives as a ``Command`` here and so is never wrapped);
    each ``{"messages": […]}`` entry has the same per-message labelling applied as
    the top-level ``dict`` shape. Any other shape is returned as-is.

    :param result: The value returned by ``ToolNode.invoke`` / ``ToolNode.ainvoke``.
    :return: The same shape with each ordinary ``ToolMessage`` wrapped in place.
    """

    def _label_messages_dict(d: dict) -> dict:
        labelled = [
            _label_one(m) if isinstance(m, ToolMessage) else m for m in d["messages"]
        ]
        return {**d, "messages": labelled}

    if isinstance(result, dict) and "messages" in result:
        return _label_messages_dict(result)
    if isinstance(result, list):
        return [
            _label_messages_dict(entry)
            if isinstance(entry, dict) and "messages" in entry
            else entry
            for entry in result
        ]
    return result


def _wrapping_tools_node(node: ToolNode) -> RunnableLambda:
    """Wrap ``node`` so its output is labelled while execution is untouched (D1/E002).

    Returns a ``RunnableLambda`` registered as the ``"tools"`` node in place of the
    bare ``ToolNode``. ``sync_node`` / ``async_node`` call the held ``ToolNode``'s
    ``invoke`` / ``ainvoke`` and post-process the return value with
    :func:`_label_tool_outputs`. There is **no** ``try``/``except`` around the
    call: an exception must propagate unchanged so ``RetryPolicy`` and
    ``error_handler`` see it exactly as if ``ToolNode`` were the node directly.
    ``async_node`` awaits ``ainvoke`` — the async execution mode
    (``docs/solutions/agent/sync-node-breaks-async-only-tools.md``) — and
    ``sync_node`` drives ``.invoke`` for the sync paths, one closure each over the
    same node so there is no second construction to drift.

    :param node: The otherwise-unchanged ``ToolNode`` to run and then label.
    :return: A ``RunnableLambda`` that runs ``node`` and labels its output.
    """

    def sync_node(state, config=None):
        return _label_tool_outputs(node.invoke(state, config))

    async def async_node(state, config=None):
        return _label_tool_outputs(await node.ainvoke(state, config))

    return RunnableLambda(sync_node, afunc=async_node)


def _tools_needing_trip(tools: list[BaseTool]) -> frozenset[str]:
    """Names of tools whose ``trip_id`` comes from ``InjectedState``.

    Derived from the annotations rather than hardcoded, so a new trip-scoped
    tool is covered the day it is written instead of the day someone remembers
    to add it to a list.

    :param tools: The sub-agent's bound tools.
    :return: The names of tools that cannot run without an active trip.
    """
    names: set[str] = set()
    for tool in tools:
        fn = tool.coroutine or tool.func
        try:
            hints = typing.get_type_hints(fn, include_extras=True)
        except Exception:  # noqa: BLE001 — never block graph build on one odd tool
            hints = {}
        # Fail open, but not silently. A tool we cannot introspect is simply
        # absent from the guard, so if it *is* trip-scoped the block quietly stops
        # happening. Both ways that occurs are caught here: annotations that will
        # not resolve (a wrapper carries the strings but not the globals that
        # define them), and annotations lost entirely (a plain wrapper). No hints
        # at all is the tell — @tool needs annotations to build a schema, so every
        # one of the 33 registered tools has some; zero means they were stripped.
        # (Not `tool.args`: that hides injected params, so it is empty for exactly
        # the trip-scoped tools this guard exists to protect.)
        if not hints:
            logger.warning(
                "[agent] cannot read annotations for tool %r — excluded from the "
                "trip guard; if it is trip-scoped it will NOT be blocked when no "
                "trip is selected",
                getattr(tool, "name", fn),
            )
            continue
        for hint in hints.values():
            for meta in getattr(hint, "__metadata__", ()):
                if isinstance(meta, InjectedState) and getattr(meta, "field", None) == (
                    "trip_id"
                ):
                    names.add(tool.name)
    return frozenset(names)


def _make_trip_guard(needing_trip: frozenset[str]):
    """Return the node that stops trip-scoped calls when no trip is selected (#113).

    Without this, the call reaches ``ToolNode`` and fails validation because the
    injected ``trip_id`` is absent. That failure is only *described* to the model
    ("ask the traveller which trip") — which leaves the outcome to whether the
    model obeys prose, and a model that ignores it can call the same tool again.
    The guard makes it a graph fact instead: ``awaiting_user`` is set exactly as
    ``needs_clarification`` sets it, so reflection ends the turn before judging it
    and the traveller is asked, deterministically.

    Runs *before* the tools node, so the blocked tool never executes.

    :param needing_trip: Names of tools that require an active trip.
    :return: A node function ``trip_guard(state) -> Command``.
    """

    def trip_guard(state: TravelAgentState) -> Command:
        if not needing_trip or state.get("trip_id"):
            return Command(goto="tools")

        last = state["messages"][-1]
        calls = list(getattr(last, "tool_calls", None) or [])
        blocked = [tc for tc in calls if tc.get("name") in needing_trip]
        if not blocked:
            return Command(goto="tools")

        logger.info(
            "[agent] trip_guard → assistant (no active trip; blocked %d call(s))",
            len(blocked),
        )
        # Every pending call needs a paired ToolMessage or the provider rejects
        # the next assistant turn — including the calls that were not blocked,
        # which are abandoned with the rest of the turn.
        messages = [
            ToolMessage(
                content=(
                    NO_ACTIVE_TRIP_MSG
                    if tc.get("name") in needing_trip
                    else (
                        "Not run — this turn is blocked on the traveller "
                        "identifying which trip they mean."
                    )
                ),
                tool_call_id=tc["id"],
                name=tc.get("name"),
                status="error",
            )
            for tc in calls
        ]
        return Command(
            goto="assistant",
            update={"awaiting_user": True, "messages": messages},
        )

    return trip_guard


def _route_after_assistant(needing_trip: frozenset[str]):
    """Route ``assistant`` to ``tools`` directly unless a call actually needs the guard.

    ``trip_guard`` only ever does two things: pass through, or block. Visiting it
    when it can only pass through wastes a super-step every round, which is what
    caps a turn's round budget under ``agent_recursion_limit`` (3 steps/round vs
    2). This decides the same thing ``trip_guard`` would decide, one edge earlier,
    so the guard is only entered when it can genuinely block.

    :param needing_trip: Names of tools that require an active trip.
    :return: A router ``route(state) -> str`` for ``add_conditional_edges``.
    """

    def route(state: TravelAgentState) -> str:
        dest = tools_condition(state)
        if dest == END:
            return END
        if not needing_trip or state.get("trip_id"):
            return "tools"
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        if any(tc.get("name") in needing_trip for tc in calls):
            return "trip_guard"
        return "tools"

    return route


def build_subagent(
    name: str,
    tools: list[BaseTool],
    resolve_model: Callable[[str | None], BaseChatModel],
    prompt: str,
    tool_fault: ToolFaultPolicy | None = None,
):
    """Compile a ReAct subgraph for one specialist domain.

    ``resolve_model`` is called per-request inside the ``assistant`` node with
    the ``AgentContext.model`` hint from the current invocation, so the chat
    model is selected at runtime rather than at build time (D1 deferred binding).
    When the runtime context carries no model hint (``None``) the resolver falls
    back to the per-agent default — preserving today's behavior.

    The shared ``communication_style`` guideline is prepended to every domain
    prompt so all user-facing replies stay warm, concise, and travel-focused —
    translating raw tool data into useful guidance rather than dumping it.

    :param name: The sub-agent's name, used as the compiled graph's node name.
    :param tools: Domain tools bound to the ``assistant`` node (filtered by
        context flags at invoke time).
    :param resolve_model: Callable resolving an ``AgentContext.model`` hint to a
        chat model, called per request inside ``assistant``.
    :param prompt: The domain-specific system prompt appended to the shared
        communication-style guideline.
    :return: The compiled ReAct subgraph for this sub-agent.
    """
    # MIN-68: every specialist can signal "blocked on the traveller" so
    # reflection ends the turn before judging the clarifying question.
    # Appended here (not in the tool registry) so it stays off MCP/manifest.
    tools = [*tools, needs_clarification]

    style = registry.get("communication_style")
    system = SystemMessage(content=f"{style}\n\n{prompt}")

    def assistant(state: TravelAgentState, runtime: Runtime[AgentContext]) -> dict:
        logger.info("[agent] node=%s (assistant)", name)
        ctx = runtime.context if runtime.context is not None else None
        allow_episodic = ctx.allow_episodic if ctx is not None else True

        model = resolve_model(None)

        # Filter the episodic-recall tool when the context disables it.
        active_tools = [
            t for t in tools if (allow_episodic or t.name != EPISODIC_TOOL_NAME)
        ]
        bound = model.bind_tools(active_tools) if active_tools else model

        tz = ctx.timezone if ctx is not None else None
        system_msg = system_with_summary(state, system)
        # Every sub-agent replies in the supervisor-detected conversation language
        # (state["language"]) — one detection, one source of truth. Also closes the
        # clarification path (MIN-68), which skips reflection's language guard.
        system_msg = with_reply_language(system_msg, state)
        # D1: ground the date before the task note so the shared style+prompt+
        # summary+language+date prefix stays identical across single-intent and
        # fan-out turns on the same day; only the per-turn task note (when
        # present) trails it.
        system_msg = ground_current_date(system_msg, tz)
        # Supervisor task folded into the leading system message, last (most
        # volatile block, changes per turn) — never appended to messages.
        system_msg = with_task_note(system_msg, state)
        response = bound.invoke(
            [
                system_msg,
                *strip_foreign_reasoning(
                    demote_midstream_system(state["messages"]), provider_of(model)
                ),
            ]
        )
        tool_calls = getattr(response, "tool_calls", None)
        if tool_calls:
            logger.info("[agent] %s → tools (%d call(s))", name, len(tool_calls))
        return {"messages": [response]}

    builder = StateGraph(TravelAgentState, context_schema=AgentContext)
    builder.add_node("assistant", assistant, retry_policy=LLM_RETRY)
    builder.add_edge(START, "assistant")

    if tools:
        # The seam (D1/E002): the "tools" node is the wrapped ToolNode's callable
        # — RunnableLambda(sync, afunc=async) around an otherwise-unchanged ToolNode
        # instance, post-processing its return value so every ordinary tool result
        # is escaped and wrapped before the model reads it. It is still ONE node
        # (no super-step added, no new node name for PROMPTS_FOR_NODE), and the
        # ToolNode's construction arguments (handle_tool_errors) and node-level
        # policies (retry_policy / error_handler) are byte-for-byte what they were,
        # so fault tolerance is framed exactly as before. Neither wrap_tool_call
        # (E001, disarms retries) nor a following node (E002, extra super-step).
        if tool_fault is None:
            builder.add_node(
                "tools",
                _wrapping_tools_node(
                    ToolNode(tools, handle_tool_errors=_tool_error_to_message)
                ),
            )
        else:
            builder.add_node(
                "tools",
                _wrapping_tools_node(
                    ToolNode(tools, handle_tool_errors=tool_fault.handle_tool_errors)
                ),
                retry_policy=tool_fault.retry_policy,
                error_handler=tool_fault.error_handler,
            )
        # #113: a trip-scoped tool called with no active trip is stopped here,
        # before it can fail arg validation and leave the outcome to whether the
        # model obeys a prose instruction. tools_condition still decides whether
        # there is tool work at all; the guard decides whether it may run.
        needing_trip = _tools_needing_trip(tools)
        builder.add_node(
            "trip_guard",
            _make_trip_guard(needing_trip),
            destinations=("tools", "assistant"),
        )
        # tools_condition -> "tools" when the last message has tool calls, else END.
        # _route_after_assistant only detours through trip_guard when a call
        # genuinely needs it, so a round with no trip-scoped call (or an active
        # trip) skips straight to "tools" instead of spending a super-step there.
        builder.add_conditional_edges(
            "assistant",
            _route_after_assistant(needing_trip),
            {"tools": "tools", "trip_guard": "trip_guard", END: END},
        )
        # The "tools" node returns control to the assistant. Wrapping happens
        # inside that node's own callable (see _wrapping_tools_node above), so no
        # intermediate node and no extra super-step is introduced; graceful_fallback
        # and trip_guard route straight to assistant via their own Command(goto=…)
        # and never pass through the wrapper (first-party, unwrapped).
        builder.add_edge("tools", "assistant")
    else:
        builder.add_edge("assistant", END)

    return builder.compile(name=name)
