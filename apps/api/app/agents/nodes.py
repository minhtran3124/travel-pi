"""Cross-cutting graph nodes: context loading, summarization, reflection, and HITL plan approval."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command, Send, interrupt

from app.agents.constants import (
    BOOKING_WRITE_TOOLS,
    DEFAULT_MAX_REVISIONS,
    REFLECTION_REVISE_NOTE,
    SYNTHESIZE_NODE,
)
from app.agents.context import AgentContext
from app.agents.copy import system_reply
from app.agents.state import TravelAgentState, with_reply_language
from app.exceptions import AppError
from app.memory.store import (
    PROFILE_KEYS,
    READ_ALL_LIMIT,
    MemoryKind,
    get_instructions,
    get_profile,
    search_memory_typed,
)
from app.memory.summarizer import should_summarize, summarize_conversation
from app.prompts.registry import registry
from app.services.trip_service import TripService
from app.tools._base import session_scope

logger = logging.getLogger(__name__)


def load_context_node(state: TravelAgentState, runtime: Runtime[AgentContext]) -> dict:
    """Best-effort: store the active trip snapshot in ``trip_context`` state field,
    and load procedural instructions from the long-term store.

    REVIEW.md M2: returning a SystemMessage via ``messages`` appends it *after* the
    HumanMessage (``add_messages`` reducer). Instead, carry the context in a plain
    state field and let ``system_with_summary`` inject it at the *front* of every
    model call — keeping the single leading SystemMessage intact for Anthropic.

    :param state: The current graph state; reads ``trip_id`` and ``user_id``.
    :param runtime: The LangGraph runtime, used to reach the long-term store.
    :return: Partial state update with ``trip_context`` and/or ``instructions``,
        whichever were successfully loaded.
    """
    # Reset the HITL plan-approval signal at the start of every fresh turn so
    # episode outcome="approved" is scoped to the turn that actually resumed
    # from the approval interrupt (issue #63). A resume turn (Command(resume=...))
    # does NOT re-enter load_context, so the approving turn keeps plan_approved=True;
    # background memory extraction reads the flag from that turn's final-state
    # snapshot before the *next* turn's load_context clears it.
    # awaiting_user is likewise single-turn (MIN-68): a clarifying question asked
    # last turn must not abandon THIS turn's fresh work.
    # GH-117 Path A: task state is also per-turn.
    result: dict = {
        "plan_approved": False,
        "awaiting_user": False,
        "tasks": [],
        "task_results": [],
    }
    trip_id = state.get("trip_id")
    owner = state.get("user_id")
    logger.info("[agent] node=load_context trip_id=%s", trip_id)
    # #118: the snapshot is loaded through the owner-scoped service, so a
    # trip_id that is not the caller's yields nothing instead of leaking a
    # title and city into the system prompt.
    if trip_id and owner:
        try:
            with session_scope() as s:
                detail = TripService(s, owner).get_trip_detail(trip_id)
            result["trip_context"] = (
                f"Active trip: {detail.title} (city: {detail.city})."
            )
        except AppError:
            pass

    # Best-effort procedural: read standing instructions from the store.
    user_id = state.get("user_id")
    store = getattr(runtime, "store", None) if runtime is not None else None
    if user_id and store is not None:
        # Read all guard-survivor instructions; the write allowlist bounds the rows.
        try:
            instrs = get_instructions(store, user_id, limit=READ_ALL_LIMIT)
            if instrs:
                result["instructions"] = "\n".join(f"- {i['text']}" for i in instrs)
                logger.info("[agent] node=load_context instructions=%d", len(instrs))
        except Exception:
            logger.exception("[agent] load_context: instruction load failed")

        try:
            profile = get_profile(store, user_id)
            if profile:
                labels = {
                    "name": "Name",
                    "gender": "Gender",
                    "travel_group": "Travelling as",
                }
                result["profile"] = "\n".join(
                    f"- {labels[k]}: {v}" for k, v in profile.items()
                )
                logger.info("[agent] node=load_context profile=%d", len(profile))
        except Exception:
            logger.exception("[agent] load_context: profile load failed")

        # Full-read preferences, excluding PROFILE_KEYS (they surface via the profile block).
        try:
            prefs = search_memory_typed(
                store, user_id, MemoryKind.PREFERENCES, limit=READ_ALL_LIMIT
            )
            non_profile = [p for p in prefs if p.key not in PROFILE_KEYS]
            if non_profile:
                result["preferences"] = "\n".join(
                    f"- {p.key}: {p.text}" for p in non_profile
                )
                logger.info(
                    "[agent] node=load_context preferences=%d", len(non_profile)
                )
        except Exception:
            logger.exception("[agent] load_context: preferences load failed")
    return result


def make_summarize_node(llm: BaseChatModel):
    """Return a node that compresses old turns into ``summary`` when long.

    :param llm: The chat model used to generate the summary.
    :return: A node function ``summarize(state) -> dict``.
    """

    def summarize(state: TravelAgentState) -> dict:
        messages = state["messages"]
        if not should_summarize(messages):
            logger.info("[agent] node=summarize (skipped — history short)")
            return {}
        summary, to_remove = summarize_conversation(messages, llm)
        logger.info("[agent] node=summarize (compressed %d messages)", len(to_remove))
        return {"summary": summary, "messages": to_remove}

    return summarize


def make_synthesize_node(llm: BaseChatModel):
    """Return a node that combines parallel worker results into one answer.

    GH-117 Path A: sorts the structured results from parallel workers and asks
    the LLM to write a single concise, helpful answer in the traveller's language.

    :param llm: Chat model used for synthesis.
    :return: A node function ``synthesize(state) -> dict``.
    """
    system = SystemMessage(
        content=(
            "You are the travel assistant. Combine the specialist findings below "
            "into one concise, helpful answer in the traveller's own language. "
            "Do not repeat raw tool data; translate findings into guidance. "
            "If the findings are empty or unhelpful, say you are still looking into it."
        )
    )

    def synthesize(state: TravelAgentState) -> dict:
        results = sorted(
            state.get("task_results") or [], key=lambda r: r.get("index", 0)
        )
        language = state.get("language", "en")
        bullets = "\n".join(
            f"- {r.get('agent', 'specialist')}: {r.get('findings', '')}"
            for r in results
        )
        prompt = (
            f"Conversation language: {language}\n\n"
            f"Specialist findings:\n{bullets}\n\n"
            "Write the final answer."
        )
        # Every reply reflects the supervisor-detected conversation language
        # (state["language"]) — one detection, one source of truth. Also covers
        # a reflection REVISE re-entering this node.
        system_msg = with_reply_language(system, state)
        answer = llm.invoke([system_msg, HumanMessage(content=prompt)]).content
        return {
            "messages": [AIMessage(content=str(answer))],
            # Must equal the synthesize node's own name so a reflection REVISE
            # (goto=current_flow) re-enters this node instead of being dropped.
            "current_flow": SYNTHESIZE_NODE,
        }

    return synthesize


def _booking_committed_this_turn(messages: list) -> bool:
    """True when a booking write tool succeeded since the last HumanMessage.

    "This turn" is the messages after the last ``HumanMessage``. A committed
    booking is a ``ToolMessage`` whose ``name`` is in ``BOOKING_WRITE_TOOLS``
    and whose ``status`` is not ``"error"`` (ToolNode sets ``"error"`` on a
    tool exception). Used by reflection to end — never REVISE — such a turn,
    so a REVISE cannot re-run the booking sub-agent and double-book (gh-193).
    """
    last_human = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human = i
    for msg in messages[last_human + 1 :]:
        if (
            isinstance(msg, ToolMessage)
            and msg.name in BOOKING_WRITE_TOOLS
            and msg.status != "error"
        ):
            return True
    return False


def make_reflection_node(
    llm: BaseChatModel, max_revisions: int = DEFAULT_MAX_REVISIONS
):
    """Return a bounded reflection node that can loop back once for a revision.

    C.2 (specs/runtime-context-config): reads ``runtime.context.allow_reflection``
    and ``runtime.context.max_revisions`` when available, replacing the
    closed-over ``max_revisions`` fallback. Default context (allow_reflection=True,
    max_revisions=1) preserves today's behavior.

    :param llm: The chat model used to judge whether the last answer needs revision.
    :param max_revisions: Fallback revision cap used when no runtime context is
        available.
    :return: A node function ``reflection(state, runtime) -> Command``.
    """
    system = SystemMessage(content=registry.get("reflection"))

    def reflection(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        # MIN-68 / #99: a turn blocked on the traveller ends with a clarifying
        # question — a necessarily "incomplete" answer the reviewer would flag
        # REVISE, re-running the sub-agent to answer WITHOUT the missing detail
        # (and, on the REST path, dropping the question for that guess). Such a
        # turn is terminal and not reviewable; end it here, before the judge call.
        if state.get("awaiting_user"):
            logger.info("[agent] reflection → END (awaiting traveller; not reviewable)")
            return Command(goto=END)

        # gh-193: a turn that already committed a booking is terminal and must
        # not be reviewed — a REVISE would route goto=current_flow ('booking')
        # and re-run the booking sub-agent, double-booking. End before the judge.
        if _booking_committed_this_turn(state["messages"]):
            logger.info(
                "[agent] reflection → END (booking committed this turn; not reviewable)"
            )
            return Command(goto=END)

        ctx = runtime.context if runtime.context is not None else None
        allow_reflection = ctx.allow_reflection if ctx is not None else True
        effective_max = ctx.max_revisions if ctx is not None else max_revisions

        revisions = state.get("revisions", 0)
        logger.info("[agent] node=reflection revisions=%d", revisions)
        if not allow_reflection or revisions >= effective_max:
            logger.info("[agent] reflection → END (no revision)")
            return Command(goto=END)

        last = state["messages"][-1]
        verdict = llm.invoke([system, last]).content

        if "REVISE" in str(verdict).upper():
            # current_flow is always set by the supervisor before a sub-agent runs
            # (so reflection is only reachable with one); the END fallback keeps
            # every emission within the node's declared destinations and routes a
            # no-flow edge case through the turn-completion path.
            target = state.get("current_flow") or END
            logger.info("[agent] reflection → %s (revise)", target)
            return Command(
                update={
                    "revisions": revisions + 1,
                    "messages": [SystemMessage(content=REFLECTION_REVISE_NOTE)],
                },
                goto=target,
            )
        logger.info("[agent] reflection → END (answer accepted)")
        return Command(goto=END)

    return reflection


def plan_node(state: TravelAgentState) -> Command:
    """Human-in-the-loop: surface a draft booking plan and wait for approval.

    ``interrupt`` pauses the graph; the caller resumes with
    ``Command(resume={"approved": True|False})``. On approval the graph
    continues to the ``booking`` sub-agent; on rejection it ends gracefully.

    :param state: The current graph state; the last message is used as the draft.
    :return: A ``Command`` routing to ``booking`` (approved) or ``END`` (rejected).
    """
    logger.info("[agent] node=plan (awaiting approval)")
    draft = state["messages"][-1].content if state["messages"] else ""
    decision = interrupt({"type": "plan_approval", "draft": draft})
    approved = not (isinstance(decision, dict) and not decision.get("approved", True))
    lang = state.get("language")
    if not approved:
        logger.info("[agent] plan → END (booking cancelled)")
        return Command(
            update={
                "messages": [AIMessage(content=system_reply("booking_cancelled", lang))]
            },
            goto=END,
        )
    logger.info("[agent] plan → booking (approved)")
    # Approval is state, not a reply: no AIMessage here. A "plan approved" line
    # would be emitted as a token and then wiped by the mapper's sub-agent
    # handoff `reset` (specs/plan-approved-line-reset); the client shows the
    # approval as an activity step instead, and the booking reply is the only
    # bubble text — matching what the router persists.
    return Command(
        update={
            # P2: signal approval so extract_memory records outcome="approved".
            "plan_approved": True,
        },
        goto="booking",
    )


def route_tasks(state: TravelAgentState) -> str | list[Send]:
    """Route from supervisor to static sub-agent, HITL plan, or parallel workers.

    GH-117 Path A: the supervisor now writes an ordered ``tasks`` list. This
    edge preserves the existing static sub-agent path for single-intent turns
    and dispatches multi-intent turns to parallel ``synthesis_worker`` instances
    via ``Send``.

    :param state: Current graph state; reads ``tasks``.
    :return: A node name for single-intent / HITL paths, a list of ``Send`` objects
        for multi-intent parallel dispatch, or ``END`` when no tasks are present.
    """
    tasks = state.get("tasks") or []
    if not tasks:
        logger.info("[agent] route_tasks → END (no tasks)")
        return END
    first = tasks[0]
    first_agent = first.get("agent", "")
    if first_agent == "booking":
        logger.info("[agent] route_tasks → plan (booking HITL)")
        return "plan"
    if len(tasks) == 1:
        logger.info("[agent] route_tasks → %s (single task)", first_agent)
        return first_agent
    logger.info("[agent] route_tasks → synthesis_workers (%d parallel)", len(tasks))
    # GH-117 Path A / Codex Comment 1: LangGraph Send does NOT merge the parent
    # state into the worker input, so the payload must carry the conversation
    # context and working state the inner specialist needs (messages, user_id,
    # trip_id, language, trip_context, etc.). We pass a shallow copy of the
    # parent state plus the task; the worker deep-copies messages before handing
    # them to the inner subgraph so the parent list is never mutated.
    return [Send("synthesis_worker", {**state, "task": t}) for t in tasks]
