"""Travel agent graph assembly.

START -> pii_guardrail -> load_context -> summarize -> supervisor -> route_tasks
    route_tasks fans out to one of:
      - a single sub-agent -> reflection
      - plan (booking HITL) -> booking -> reflection
      - Send(synthesis_worker) x N -> synthesize -> reflection
    reflection -> <sub-agent> | synthesize | END
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore

from app.agents.constants import SYNTHESIZE_NODE
from app.agents.context import AgentContext
from app.agents.guardrails import pii_guardrail_node
from app.agents.nodes import (
    load_context_node,
    make_reflection_node,
    make_summarize_node,
    make_synthesize_node,
    plan_node,
    route_tasks,
)
from app.agents.prompt_map import prompt_versions_snapshot
from app.agents.retry import LLM_RETRY
from app.agents.state import TravelAgentState
from app.agents.subagents.booking import build_booking
from app.agents.subagents.budget import build_budget
from app.agents.subagents.concierge import build_concierge
from app.agents.subagents.journal import build_journal
from app.agents.subagents.planner import build_planner
from app.agents.subagents.synthesis_worker import build_synthesis_worker
from app.agents.supervisor import SUBAGENTS, make_supervisor
from app.clients.llm import FAST_AGENTS, get_agent_llm
from app.core.agent_config_cache import AgentConfigCache
from app.prompts.registry import registry
from app.research.launcher import build_research_service, make_research_node

logger = logging.getLogger(__name__)


def build_graph(
    *,
    llm: BaseChatModel | None = None,
    fast_llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
):
    """Compile the travel agent graph; inject ``llm``/``fast_llm``/backends for tests.

    Each node resolves its own model via ``get_agent_llm``; an injected fake
    overrides the whole tier regardless of the per-request ``ctx_model`` hint.
    """

    def pick(name: str) -> BaseChatModel:
        """Fixed model for non-sub-agent nodes (supervisor, summarize, reflection)."""
        if name in FAST_AGENTS:
            return fast_llm if fast_llm is not None else get_agent_llm(name)
        return llm if llm is not None else get_agent_llm(name)

    def resolver_for(name: str) -> Callable[[str | None], BaseChatModel]:
        """Deferred per-request resolver for sub-agent nodes.

        The ReAct ``assistant`` node re-runs on every tool round-trip, so built
        models are memoized per ``ctx_model`` in this closure (a fresh cache per
        ``build_graph``, so injected fakes never populate it).
        """
        cache: dict[str | None, BaseChatModel] = {}

        def resolve(ctx_model: str | None) -> BaseChatModel:
            fake = fast_llm if name in FAST_AGENTS else llm
            if fake is not None:
                return fake
            if ctx_model not in cache:
                cache[ctx_model] = get_agent_llm(name)
            return cache[ctx_model]

        return resolve

    builder = StateGraph(TravelAgentState, context_schema=AgentContext)
    # PII guardrail runs first, before any model call, checkpointer write, or the
    # post-response memory extractor reads the turn.
    builder.add_node("pii_guardrail", pii_guardrail_node)
    builder.add_node("load_context", load_context_node)
    builder.add_node(
        "summarize", make_summarize_node(pick("summarize")), retry_policy=LLM_RETRY
    )
    builder.add_node(
        "supervisor",
        make_supervisor(pick("supervisor")),
        retry_policy=LLM_RETRY,
    )
    # HITL plan-approval gate: fires before booking commits anything destructive.
    builder.add_node("plan", plan_node, destinations=("booking", "__end__"))
    builder.add_node("planner", build_planner(resolver_for("planner")))
    builder.add_node("concierge", build_concierge(resolver_for("concierge")))
    builder.add_node("journal", build_journal(resolver_for("journal")))
    builder.add_node("booking", build_booking(resolver_for("booking")))
    builder.add_node("budget", build_budget(resolver_for("budget")))
    # Deep-trip-research launcher: a specialist-shaped node (no LLM) named
    # "research" so the `for name in SUBAGENTS` loop and reflection's destinations
    # cover it with no hand-written edge. Off unless `research_enabled` (design §6).
    builder.add_node(
        "research", make_research_node(lambda: build_research_service(store))
    )

    def worker_resolve(agent_name: str, ctx_model: str | None = None) -> BaseChatModel:
        """Resolve the per-specialist model at worker runtime (from ``state["task"]``)."""
        return resolver_for(agent_name)(ctx_model)

    builder.add_node(
        "synthesis_worker",
        build_synthesis_worker(worker_resolve),
    )
    builder.add_node(
        SYNTHESIZE_NODE,
        make_synthesize_node(pick(SYNTHESIZE_NODE)),
        retry_policy=LLM_RETRY,
    )
    builder.add_node(
        "reflection",
        make_reflection_node(pick("reflection")),
        destinations=(*SUBAGENTS, SYNTHESIZE_NODE, END),
        retry_policy=LLM_RETRY,
    )

    builder.add_edge(START, "pii_guardrail")
    builder.add_edge("pii_guardrail", "load_context")
    builder.add_edge("load_context", "summarize")
    builder.add_edge("summarize", "supervisor")
    # Routes single intents to a sub-agent, booking through the HITL plan node, and
    # multi-intent turns to parallel synthesis workers via Send.
    builder.add_conditional_edges("supervisor", route_tasks)
    # Every sub-agent edges straight to reflection; a clarifying turn ends early via
    # reflection's own awaiting_user guard.
    for name in SUBAGENTS:
        builder.add_edge(name, "reflection")
    # Parallel workers converge on synthesize, then reflection.
    builder.add_edge("synthesis_worker", SYNTHESIZE_NODE)
    builder.add_edge(SYNTHESIZE_NODE, "reflection")

    compiled = builder.compile(checkpointer=checkpointer, store=store)
    # Memory extraction runs as a background task, not in-graph; attach the resolved
    # LLM here so routers reuse the same injection seam.
    compiled.extract_memory_llm = pick("extract_memory")
    # Snapshot prompt versions at build so attribution reports the versions this graph
    # baked in, not whatever ``active.yaml`` says at turn time.
    compiled.prompt_versions = prompt_versions_snapshot(registry)
    return compiled


def resolve_travel_graph(app):
    """Return the compiled graph, rebuilding it if the config generation changed.

    A rebuild reuses the process-lifetime checkpointer + store so conversation state
    is preserved. Falls back to the existing graph when backends are absent or a
    rebuild fails.
    """
    graph = getattr(app.state, "travel_graph", None)
    checkpointer = getattr(app.state, "agent_checkpointer", None)
    store = getattr(app.state, "agent_store", None)
    if graph is None or checkpointer is None:
        return graph

    generation = AgentConfigCache.generation()
    if generation == getattr(app.state, "travel_graph_gen", None):
        return graph

    try:
        app.state.travel_graph = build_graph(checkpointer=checkpointer, store=store)
        app.state.travel_graph_gen = generation
        logger.info("Agent graph rebuilt for config generation %d", generation)
    except Exception:
        logger.exception("Agent graph rebuild failed; keeping the previous graph")
    return app.state.travel_graph
