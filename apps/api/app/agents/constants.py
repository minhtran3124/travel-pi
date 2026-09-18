"""Agent-domain constants shared across the agent layer."""

from __future__ import annotations

from app.enums import Tier

DEFAULT_TIER: Tier = Tier.FREE

ALL_SUBAGENTS: tuple[str, ...] = (
    "planner",
    "concierge",
    "journal",
    "booking",
    "budget",
)
# Sub-agents unavailable on the free tier (routing is restricted to the rest).
PREMIUM_ONLY_SUBAGENTS: frozenset[str] = frozenset({"booking"})

# Convergence node label. Must equal a declared routing destination or LangGraph
# silently drops a reflection REVISE routed back via ``goto=current_flow``.
SYNTHESIZE_NODE = "synthesize"

# Max sub-agent tasks the supervisor may schedule in one turn; bounded to keep the
# parent graph inside ``agent_recursion_limit`` with headroom for the revise loop.
MAX_LEDGER_STEPS = 4

# Graph nodes that default to the cheap ``fast_llm_model`` when config omits ``model``.
FAST_AGENTS: frozenset[str] = frozenset(
    {
        "summarize",
        "journal",
        "budget",
        "reflection",
        "extract_memory",
        "date_resolution",
        "trip_research_grader",
    }
)

# Episodic-recall tool; gated off when ``AgentContext.allow_episodic`` is False.
EPISODIC_TOOL_NAME = "recall_past_trips"

# Write tools whose ToolMessage marks a committed booking. Reflection ends the turn
# (never REVISEs) when one succeeded this turn, so a REVISE cannot double-book.
BOOKING_WRITE_TOOLS: frozenset[str] = frozenset({"book_flight", "book_hotel"})

# Default revise-loop cap; overridden per-mode via ``AgentContext.max_revisions``.
DEFAULT_MAX_REVISIONS = 1

# Note reflection injects when sending an answer back for revision. A SystemMessage
# (never HumanMessage) so language-detection and "latest traveller message" rules don't misfire.
REFLECTION_REVISE_NOTE = (
    "Please improve your previous answer. This is an internal review note, not "
    "a message from the traveller — keep replying in the traveller's own language."
)

# Folded into the specialist's leading SystemMessage (never a HumanMessage, which
# would be mistaken for the traveller's latest message) when a task is scheduled.
TASK_NOTE_PREAMBLE = (
    "Internal routing note from the supervisor, not a message from the "
    "traveller. Answer it against the conversation that follows: use the facts, "
    "dates and identifiers already established there — do not answer "
    "generically. Keep replying in the traveller's own language. Your task for "
    "this turn:\n\n"
)

# Emitted by trip_guard when a trip-scoped tool runs with no active trip. Model
# instructions, not verbatim text: never asks for the trip id (an unseen UUID).
NO_ACTIVE_TRIP_MSG = (
    "Not run: no trip is selected for this conversation, and this tool cannot "
    "run without one. This is NOT an outage and retrying will fail identically. "
    "Ask the traveller which trip they mean — by destination and rough dates, "
    "never by id (they have never seen one). Offer to start a new trip if they "
    "do not have one yet, and confirm the destination and dates back to them "
    "before acting, so a wrong guess is caught before it reaches their data."
)

# Code-side handle for the assistant's name (persona lives in prompts).
ASSISTANT_NAME = "Tin"

# English SOURCE text; emit via ``app.agents.copy.system_reply`` for translation.
BOOKING_UPGRADE_MSG = (
    "Booking is a premium feature. Please upgrade your plan to book trips."
)

NOT_SURE_MSG = "I'm not sure how to help with that yet."

# HITL plan reject outcome. Approval has no reply line: it is state (plan_approved).
PLAN_CANCELLED_MSG = "Booking cancelled as requested."

# Safety net returned when the run fails before producing any reply, so the chat
# bubble is never empty and the request never 500s without a readable message.
AGENT_ERROR_FALLBACK_MSG = (
    "I ran into a problem handling that request and couldn't finish my reply. "
    "Please try again in a moment."
)
