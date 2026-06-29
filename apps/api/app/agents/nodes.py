"""Cross-cutting graph nodes (specs/travel-agent Task 5.3).

- ``load_context_node``: injects the current trip snapshot as context.
- ``make_summarize_node``: compresses long histories (sliding window).
- ``make_reflection_node``: bounded self-correction — critiques the last answer
  and loops back to the active sub-agent once if it judges it inadequate.
- ``plan_node``: human-in-the-loop checkpoint via ``interrupt`` for plan approval.
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
from app.memory.summarizer import should_summarize, summarize_conversation
from app.prompts.registry import registry
from app.services.trip_service import TripService
from app.tools._base import session_scope

logger = logging.getLogger(__name__)


def load_context_node(state: TravelAgentState) -> dict:
    """Best-effort: store the active trip snapshot in ``trip_context`` state field.

    REVIEW.md M2: returning a SystemMessage via ``messages`` appends it *after* the
    HumanMessage (``add_messages`` reducer).  Instead, carry the context in a plain
    state field and let ``system_with_summary`` inject it at the *front* of every
    model call — keeping the single leading SystemMessage intact for Anthropic.
    """
    trip_id = state.get("trip_id")
    if not trip_id:
        return {}
    try:
        with session_scope() as s:
            detail = TripService(s).get_trip_detail(trip_id)
        context = (
            f"Active trip: {detail.title} (city: {detail.city}). "
            f"Use the trip tools with trip_id={trip_id} for details."
        )
        return {"trip_context": context}
    except AppError:
        return {}


def make_summarize_node(llm: BaseChatModel):
    """Return a node that compresses old turns into ``summary`` when long."""

    def summarize(state: TravelAgentState) -> dict:
        messages = state["messages"]
        if not should_summarize(messages):
            return {}
        summary, to_remove = summarize_conversation(messages, llm)
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
    """
    system = SystemMessage(content=registry.get("reflection"))

    def reflection(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        ctx = runtime.context if runtime.context is not None else None
        allow_reflection = ctx.allow_reflection if ctx is not None else True
        effective_max = ctx.max_revisions if ctx is not None else max_revisions

        revisions = state.get("revisions", 0)
        if not allow_reflection or revisions >= effective_max:
            return Command(goto=END)
        last = state["messages"][-1]
        verdict = llm.invoke([system, last]).content
        if "REVISE" in str(verdict).upper():
            return Command(
                update={
                    "revisions": revisions + 1,
                    "messages": [
                        HumanMessage(content="Please improve your previous answer.")
                    ],
                },
                goto=state.get("current_flow") or END,
            )
        return Command(goto=END)

    return reflection


def plan_node(state: TravelAgentState) -> Command:
    """Human-in-the-loop: surface a draft booking plan and wait for approval.

    ``interrupt`` pauses the graph; the caller resumes with
    ``Command(resume={"approved": True|False})``.  On approval the graph
    continues to the ``booking`` sub-agent; on rejection it ends gracefully.
    """
    draft = state["messages"][-1].content if state["messages"] else ""
    decision = interrupt({"type": "plan_approval", "draft": draft})
    approved = not (isinstance(decision, dict) and not decision.get("approved", True))
    if not approved:
        return Command(
            update={"messages": [AIMessage(content="Booking cancelled as requested.")]},
            goto=END,
        )
    return Command(
        update={
            "messages": [AIMessage(content="Plan approved. Proceeding with booking.")]
        },
        goto="booking",
    )
