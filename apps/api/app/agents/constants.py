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

# --- task ledger (P1) -----------------------------------------------------
# Max total sub-agent runs the supervisor may schedule in ONE turn — the
# primary target plus up to ``MAX_LEDGER_STEPS - 1`` ordered follow-ons drained
# by ``dispatch_next``. Bounded because each sub-agent is an isolated ReAct
# subgraph (own recursion budget), so the parent graph spends ~2 super-steps
# per step (dispatch_next + the subagent node); 4 steps stay well inside
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
# Shown when a free user is routed to a premium-only sub-agent (booking).
BOOKING_UPGRADE_MSG = (
    "Booking is a premium feature. Please upgrade your plan to book trips."
)

# Always-on safety net: returned to the user when the agent run fails before it
# could produce any reply (tool outage, LLM error, or a ReAct loop that exhausted
# the recursion limit on repeated tool errors). Guarantees the chat bubble is
# never empty / the request never 500s without a readable message.
AGENT_ERROR_FALLBACK_MSG = (
    "I ran into a problem handling that request and couldn't finish my reply. "
    "Please try again in a moment."
)
