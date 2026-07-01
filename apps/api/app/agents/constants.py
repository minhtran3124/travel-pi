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

# Graph nodes that default to the cheap ``fast_llm_model`` when a per-agent
# config omits ``model``. Everything else defaults to the main ``llm_model``.
FAST_AGENTS: frozenset[str] = frozenset(
    {"summarize", "journal", "budget", "reflection", "extract_memory"}
)

# --- tooling --------------------------------------------------------------
# Name of the RAG retrieval tool (app/tools/rag_tools.py); gated off when
# ``AgentContext.allow_rag`` is False (fast mode / free-tier constraint).
RAG_TOOL_NAME = "search_destination_knowledge"

# Name of the episodic-recall tool (app/tools/memory_tools.py); gated off when
# ``AgentContext.allow_episodic`` is False (mirrors the RAG filter in _base.py).
EPISODIC_TOOL_NAME = "recall_past_trips"

# --- reflection -----------------------------------------------------------
# Default revise-loop cap; overridden per-mode via ``AgentContext.max_revisions``.
DEFAULT_MAX_REVISIONS = 1

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
