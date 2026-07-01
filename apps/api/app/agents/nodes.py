"""Cross-cutting graph nodes (specs/travel-agent Task 5.3).

- ``load_context_node``: injects the current trip snapshot as context + procedural
  instructions from the store.
- ``make_summarize_node``: compresses long histories (sliding window).
- ``make_reflection_node``: bounded self-correction — critiques the last answer
  and loops back to the active sub-agent once if it judges it inadequate.
- ``plan_node``: human-in-the-loop checkpoint via ``interrupt`` for plan approval.
- ``make_extract_memory_node``: post-turn background memory extraction (P1).
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from app.agents.constants import DEFAULT_MAX_REVISIONS
from app.agents.context import AgentContext
from app.agents.state import TravelAgentState
from app.exceptions import AppError
from app.memory.extractor import extract_memories
from app.memory.store import (
    get_instructions,
    upsert_episode,
    upsert_instruction,
    upsert_preference,
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
    result: dict = {}
    trip_id = state.get("trip_id")
    logger.info("[agent] node=load_context trip_id=%s", trip_id)
    if trip_id:
        try:
            with session_scope() as s:
                detail = TripService(s).get_trip_detail(trip_id)
            result["trip_context"] = (
                f"Active trip: {detail.title} (city: {detail.city}). "
                f"Use the trip tools with trip_id={trip_id} for details."
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
        ctx = runtime.context if runtime.context is not None else None
        allow_reflection = ctx.allow_reflection if ctx is not None else True
        effective_max = ctx.max_revisions if ctx is not None else max_revisions

        revisions = state.get("revisions", 0)
        logger.info("[agent] node=reflection revisions=%d", revisions)
        if not allow_reflection or revisions >= effective_max:
            logger.info("[agent] reflection → extract_memory (no revision)")
            return Command(goto="extract_memory")
        last = state["messages"][-1]
        verdict = llm.invoke([system, last]).content
        if "REVISE" in str(verdict).upper():
            # current_flow is always set by the supervisor before a sub-agent runs
            # (so reflection is only reachable with one); the "extract_memory"
            # fallback keeps every emission within the node's declared destinations
            # and routes a no-flow edge case through the turn-completion path.
            target = state.get("current_flow") or "extract_memory"
            logger.info("[agent] reflection → %s (revise)", target)
            return Command(
                update={
                    "revisions": revisions + 1,
                    "messages": [
                        HumanMessage(content="Please improve your previous answer.")
                    ],
                },
                goto=target,
            )
        logger.info("[agent] reflection → extract_memory (answer accepted)")
        return Command(goto="extract_memory")

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


def make_extract_memory_node(llm: BaseChatModel):
    """Return a post-turn background memory extraction node (P1).

    Gated by ``runtime.context.allow_memory_write`` — skips entirely for FAST
    mode. Best-effort: any error is swallowed so a failed extraction never
    breaks the turn.

    :param llm: The chat model used to extract preferences/instructions/episodes.
    :return: A node function ``extract_memory(state, runtime) -> dict``.
    """

    def extract_memory(state: TravelAgentState, runtime: Runtime[AgentContext]) -> dict:
        ctx = runtime.context if runtime.context is not None else None
        allow_write = ctx.allow_memory_write if ctx is not None else True
        if not allow_write:
            logger.info(
                "[agent] node=extract_memory (skipped — allow_memory_write=False)"
            )
            return {}

        user_id = state.get("user_id")
        store = getattr(runtime, "store", None)
        if not user_id or store is None:
            logger.info("[agent] node=extract_memory (skipped — no user_id or store)")
            return {}

        try:
            extracted = extract_memories(state["messages"], llm)
            for pref in extracted.preferences:
                upsert_preference(store, user_id, pref["key"], {"text": pref["text"]})
            for instr in extracted.instructions:
                upsert_instruction(
                    store, user_id, instr["key"], {"text": instr["text"]}
                )
            # P2: persist episodes with rich metadata. A turn that passed the HITL
            # plan-approval gate (plan_approved=True) records outcome="approved";
            # otherwise the extractor's default ("proposed") stands.
            trip_id = state.get("trip_id")
            plan_approved = state.get("plan_approved", False)
            for ep in extracted.episodes:
                key = ep.get("key") or trip_id or "episode"
                outcome = "approved" if plan_approved else ep.get("outcome", "proposed")
                upsert_episode(
                    store,
                    user_id,
                    key,
                    {
                        "text": ep["text"],
                        "trip_id": trip_id,
                        "city": ep.get("city"),
                        "outcome": outcome,
                    },
                )
            logger.info(
                "[agent] node=extract_memory preferences=%d instructions=%d episodes=%d",
                len(extracted.preferences),
                len(extracted.instructions),
                len(extracted.episodes),
            )
        except Exception:
            logger.exception("[agent] node=extract_memory: write failed")
        return {}

    return extract_memory
