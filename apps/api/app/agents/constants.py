"""Agent-domain constants — one home for the flat, tunable values.

Enum-valued *types* live in ``app/enums.py`` (``Tier``, …); this module holds
the plain constants the agent layer shares across modules: the safe tier
default, the canonical sub-agent name sets, the fast-tier node set, the RAG
tool name, the reflection cap, and user-facing copy. Keeping them together
makes them easy to find and change without hunting through nodes.

Import from here rather than redefining; the previous home modules now re-export
these so existing import paths keep working.
"""

from __future__ import annotations

from app.enums import Tier

# --- tier resolution default ------------------------------------------------
# Unknown/None tier falls back to this in ``resolve_agent_context``.
DEFAULT_TIER: Tier = Tier.FREE

# --- sub-agent inventory --------------------------------------------------
# Canonical specialist sub-agent names — the single source of truth.
ALL_SUBAGENTS: tuple[str, ...] = (
    "planner",
    "concierge",
    "journal",
    "booking",
    "budget",
)
# Sub-agents unavailable on the free tier (routing is restricted to the rest).
PREMIUM_ONLY_SUBAGENTS: frozenset[str] = frozenset({"booking"})

# Name of the parallel-synthesis convergence node (GH-117 Path A). Shared so the
# node registration, reflection's declared destinations, the worker/synthesize
# edges, and the ``current_flow`` label the synthesize node emits all reference
# ONE string. They MUST agree: reflection routes a REVISE back via
# ``goto=current_flow``, and a label that is not a declared destination is
# silently dropped by LangGraph (the revision is wasted). See
# specs/fix-reflection-synthesize-goto.
SYNTHESIZE_NODE = "synthesize"

# --- task fan-out (P1) ----------------------------------------------------
# Max total sub-agent tasks the supervisor may schedule in ONE turn — dispatched
# as parallel ``synthesis_worker`` instances (GH-117 Path A) that converge on
# ``synthesize``. Bounded because each worker is an isolated ReAct subgraph (own
# recursion budget); the cap keeps the parent graph well inside
# ``agent_recursion_limit`` (25) with headroom for the reflection revise loop.
# The supervisor truncates an over-long model-emitted plan to this in code.
MAX_LEDGER_STEPS = 4

# Graph nodes that default to the cheap ``fast_llm_model`` when a per-agent
# config omits ``model``. Everything else defaults to the main ``llm_model``.
FAST_AGENTS: frozenset[str] = frozenset(
    {
        "summarize",
        "journal",
        "budget",
        "reflection",
        "extract_memory",
        "date_resolution",
    }
)

# --- tooling --------------------------------------------------------------
# Name of the episodic-recall tool (app/tools/memory_tools.py); gated off when
# ``AgentContext.allow_episodic`` is False (mirrors the RAG filter in _base.py).
EPISODIC_TOOL_NAME = "recall_past_trips"

# --- reflection -----------------------------------------------------------
# Default revise-loop cap; overridden per-mode via ``AgentContext.max_revisions``.
DEFAULT_MAX_REVISIONS = 1

# Internal note reflection injects into ``state["messages"]`` when it sends an
# answer back for revision. Shared so the REST reply-assembly can recognise a
# superseded draft (the answer immediately before this note) without coupling to
# the wording. A SystemMessage (never HumanMessage) so language-detection and
# "the traveller's latest message" prompt rules don't misfire.
REFLECTION_REVISE_NOTE = (
    "Please improve your previous answer. This is an internal review note, not "
    "a message from the traveller — keep replying in the traveller's own language."
)

# --- trip selection -------------------------------------------------------
# Emitted by the trip_guard node (app/agents/subagents/_base.py) when the model
# calls a trip-scoped tool with no active trip in state (#113). Instructions to
# the MODEL, not text shown verbatim: the reply must be in the traveller's own
# language. Never asks for the trip id — the traveller has never seen one; the
# id is a UUID the system assigns, so asking for it is a dead end.
NO_ACTIVE_TRIP_MSG = (
    "Not run: no trip is selected for this conversation, and this tool cannot "
    "run without one. This is NOT an outage and retrying will fail identically. "
    "Ask the traveller which trip they mean — by destination and rough dates, "
    "never by id (they have never seen one). Offer to start a new trip if they "
    "do not have one yet, and confirm the destination and dates back to them "
    "before acting, so a wrong guess is caught before it reaches their data."
)

# --- user-facing copy -----------------------------------------------------
# The assistant's name (persona lives in prompts/communication_style; this is
# the code-side handle for text produced outside the LLM reply path).
ASSISTANT_NAME = "Tin"

# English SOURCE text only. Emit through ``app.agents.copy.system_reply`` so
# the traveller gets it in the conversation language (translated once, cached).
# Shown when a free user is routed to a premium-only sub-agent (booking).
BOOKING_UPGRADE_MSG = (
    "Booking is a premium feature. Please upgrade your plan to book trips."
)

# Supervisor could not map the message to any specialist.
NOT_SURE_MSG = "I'm not sure how to help with that yet."

# HITL plan node outcomes (app/agents/nodes.py).
PLAN_CANCELLED_MSG = "Booking cancelled as requested."
PLAN_APPROVED_MSG = "Plan approved. Proceeding with booking."

# Always-on safety net: returned to the user when the agent run fails before it
# could produce any reply (tool outage, LLM error, or a ReAct loop that exhausted
# the recursion limit on repeated tool errors). Guarantees the chat bubble is
# never empty / the request never 500s without a readable message.
AGENT_ERROR_FALLBACK_MSG = (
    "I ran into a problem handling that request and couldn't finish my reply. "
    "Please try again in a moment."
)
