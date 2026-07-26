"""Cross-cutting graph nodes (specs/travel-agent Task 5.3).

- ``load_context_node``: injects the current trip snapshot as context + procedural
  instructions from the store.
- ``make_summarize_node``: compresses long histories (sliding window).
- ``plan_node``: human-in-the-loop checkpoint via ``interrupt`` for plan approval.
- ``dispatch_next``: pure-code ledger drainer — pops the next queued follow-on
  sub-agent from the ordered ledger (P1), or ends the turn once the ledger is
  empty (MIN-65 D4).

Post-turn memory extraction no longer runs in-graph — see
``app.memory.extraction_runner.run_memory_extraction``, scheduled by routers as a
background task after the response is sent.
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app.agents.constants import ALL_SUBAGENTS
from app.agents.context import AgentContext
from app.agents.state import TravelAgentState
from app.exceptions import AppError
from app.memory.store import (
    PROFILE_KEYS,
    MemoryKind,
    get_instructions,
    get_profile,
    search_memory_typed,
)
from app.memory.summarizer import should_summarize, summarize_conversation
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
    # last turn must not abandon THIS turn's fresh ledger.
    result: dict = {"plan_approved": False, "awaiting_user": False}
    trip_id = state.get("trip_id")
    logger.info("[agent] node=load_context trip_id=%s", trip_id)
    if trip_id:
        try:
            with session_scope() as s:
                detail = TripService(s).get_trip_detail(trip_id)
            result["trip_context"] = (
                f"Active trip: {detail.title} (city: {detail.city})."
            )
        except AppError:
            pass

    # Best-effort procedural: read standing instructions from the store.
    user_id = state.get("user_id")
    store = getattr(runtime, "store", None) if runtime is not None else None
    if user_id and store is not None:
        try:
            instrs = get_instructions(store, user_id)
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

        # Best-effort: recency-ordered full-read of traveller preferences (MIN-65
        # DESIGN D2 — bounded full-read beats semantic search at this store size),
        # excluding PROFILE_KEYS since those already surface via the profile block
        # above. search_memory_typed (not search_preferences) is used because it
        # preserves each preference's store key, needed both to filter and to
        # format the "- {key}: {value}" lines below.
        try:
            prefs = search_memory_typed(store, user_id, MemoryKind.PREFERENCES, limit=8)
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
    if not approved:
        logger.info("[agent] plan → END (booking cancelled)")
        return Command(
            update={"messages": [AIMessage(content="Booking cancelled as requested.")]},
            goto=END,
        )
    logger.info("[agent] plan → booking (approved)")
    return Command(
        update={
            "messages": [AIMessage(content="Plan approved. Proceeding with booking.")],
            # P2: signal approval so extract_memory records outcome="approved".
            "plan_approved": True,
        },
        goto="booking",
    )


def dispatch_next(state: TravelAgentState) -> Command:
    """Drain the next step of the task ledger, or end the turn (MIN-65 D4).

    Pure-code ledger drainer — no LLM call. Every sub-agent's static edge points
    here instead of straight to ``END``, so a supervisor that queued an ordered
    ledger of follow-on sub-agents in ``pending_flows`` (P1; capped at
    ``MAX_LEDGER_STEPS - 1`` entries, never "booking" — see
    ``app.agents.supervisor``) gets each queued sub-agent run in order, in the
    same turn. Each queued sub-agent sees the previous ones' messages in state,
    so it naturally continues the thread (e.g. "the flight picked above").

    When ``awaiting_user`` is set (a sub-agent called the ``needs_clarification``
    tool), the remaining queue is abandoned and the turn ends here (MIN-68).

    :param state: The current graph state; reads ``pending_flows``.
    :return: A ``Command`` routing to the next queued sub-agent (draining the
        queue and updating ``current_flow``), or to ``END`` once empty.
    """
    pending = state.get("pending_flows") or []
    # MIN-68: a sub-agent that called needs_clarification is blocked on the
    # traveller — running the queued follow-ons would spend LLM/tool calls on
    # output the traveller never sees (the reply is the clarifying question).
    # Abandon the rest of the plan; next turn re-plans with the answer.
    if state.get("awaiting_user"):
        logger.info(
            "[agent] dispatch_next → END (awaiting traveller; "
            "abandoning %d queued step(s))",
            len(pending),
        )
        return Command(update={"pending_flows": []}, goto=END)
    if pending:
        nxt, rest = pending[0], pending[1:]
        # Fail safe rather than trusting the caller: the supervisor is the
        # only writer of pending_flows and already excludes "booking" and
        # tier-restricted agents, but dispatch_next is a second entry point
        # into every sub-agent and must not blindly honour a queue entry
        # that would bypass the booking HITL interrupt if that upstream
        # guard ever regressed (ce-code-review finding, 4 independent
        # reviewers).
        if nxt not in ALL_SUBAGENTS or nxt == "booking":
            logger.error(
                "[agent] dispatch_next refusing illegal queued flow: %r "
                "(pending_flows should never contain this) → END",
                nxt,
            )
            return Command(update={"pending_flows": []}, goto=END)
        logger.info("[agent] dispatch_next → %s (pending=%d)", nxt, len(rest))
        return Command(update={"current_flow": nxt, "pending_flows": rest}, goto=nxt)
    logger.info("[agent] dispatch_next → END (queue empty)")
    return Command(goto=END)
