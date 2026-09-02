"""Travel agent graph assembly (specs/travel-agent Task 5.4).

Wires the full agentic graph:

    START -> pii_guardrail -> load_context -> summarize -> supervisor -> route_tasks
        route_tasks fans out to one of:
          - a single sub-agent -> reflection
          - plan (booking HITL) -> booking -> reflection
          - Send(synthesis_worker) x N -> synthesize -> reflection
        reflection -> <sub-agent> | synthesize | END

The ``pii_guardrail`` entry node redacts email/credit-card PII from the user's
turn before any LLM provider, checkpointer, or memory extractor sees it.
``route_tasks`` routes the supervisor's task list: a single intent goes straight
to its sub-agent, booking detours through the HITL ``plan`` node, and a
multi-intent turn is dispatched to parallel ``synthesis_worker`` instances that
converge on ``synthesize``. Each sub-agent is a ReAct subgraph that self-corrects
on tool errors and edges directly to ``reflection`` (a clarifying turn ends early
via reflection's ``awaiting_user`` guard, MIN-68). Reflection adds a bounded
answer-quality loop. Checkpointer + store make it stateful across turns/sessions.
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

logger = logging.getLogger(__name__)


def build_graph(
    *,
    llm: BaseChatModel | None = None,
    fast_llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
):
    """Compile the travel agent graph. Inject fakes/backends for tests.

    Each node resolves its own model via ``get_agent_llm`` so providers/models
    can be tuned per agent (DB ``agent_config`` via ``AgentConfigCache``). When tests inject
    ``llm`` / ``fast_llm``, those override the whole main / fast tier — the node
    keeps using the injected fake exactly as before.

    C.1: Sub-agent nodes receive a ``resolver_for(name)`` callable instead of a
    fixed model. When a fake is injected it is returned regardless of the
    per-request ``ctx_model`` hint, so all existing tests stay green.

    :param llm: Fake/override chat model for main-tier nodes (tests).
    :param fast_llm: Fake/override chat model for fast-tier nodes (tests).
    :param checkpointer: Checkpoint saver for cross-turn/session state.
    :param store: Long-term store backing episodic/RAG tools.
    :return: The compiled travel agent graph.
    """

    def pick(name: str) -> BaseChatModel:
        """Fixed model for non-sub-agent nodes (supervisor, summarize, reflection).

        :param name: The node's name, used to check ``FAST_AGENTS`` membership.
        :return: The injected fake when set, else the node's configured chat model.
        """
        if name in FAST_AGENTS:
            return fast_llm if fast_llm is not None else get_agent_llm(name)
        return llm if llm is not None else get_agent_llm(name)

    def resolver_for(name: str) -> Callable[[str | None], BaseChatModel]:
        """Deferred resolver for sub-agent nodes — called per request (D1).

        When a fake is injected (tests), it is returned regardless of
        ``ctx_model`` → all existing tests stay green. In prod, ``ctx_model`` is
        always ``None`` (the per-request model hint was removed in MIN-43) and
        ``get_agent_llm(name)`` resolves the DB/env-backed config.

        The ReAct ``assistant`` node re-runs on every tool round-trip, so this
        resolver is hit many times per turn. Built models are memoized per
        ``ctx_model`` for the life of this compiled graph (built once in
        ``lifespan``), so ``init_chat_model`` runs at most once per distinct
        hint instead of once per iteration. The cache lives in the closure, so
        each ``build_graph`` call (e.g. per test) gets a fresh one and injected
        fakes never populate it.

        :param name: The sub-agent's name (looked up in ``FAST_AGENTS`` and
            passed through to ``get_agent_llm``).
        :return: A callable resolving a per-request ``ctx_model`` hint to a
            chat model.
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
    # PII guardrail runs first so email/card are redacted before any model call,
    # before persistence to the checkpointer, and before the post-response memory
    # extractor reads the turn.
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

    def worker_resolve(agent_name: str, ctx_model: str | None = None) -> BaseChatModel:
        """Resolve the per-specialist model for parallel synthesis workers.

        Mirrors ``resolver_for`` but selects the specialist at worker runtime
        (the worker learns which agent it is running from ``state["task"]``).
        """
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
    # GH-117 Path A: supervisor emits an ordered task list; a conditional edge
    # routes single-intent turns to the existing static sub-agent nodes, routes
    # booking through the HITL plan node, and dispatches multi-intent turns to
    # parallel synthesis workers via Send.
    builder.add_conditional_edges("supervisor", route_tasks)
    # Every sub-agent edges straight to reflection. A clarifying turn ends early
    # via reflection's own awaiting_user guard (MIN-68); the plan/HITL booking
    # detour keeps its own Command(goto="booking"|END) topology.
    for name in SUBAGENTS:
        builder.add_edge(name, "reflection")
    # GH-117 Path A: parallel workers converge on synthesize, then reflection.
    builder.add_edge("synthesis_worker", SYNTHESIZE_NODE)
    builder.add_edge(SYNTHESIZE_NODE, "reflection")
    # plan -> booking | END is a Command(goto=...) after interrupt resumes.
    # reflection -> sub-agent | END is a Command(goto=...).

    compiled = builder.compile(checkpointer=checkpointer, store=store)
    # Memory extraction no longer runs in-graph (specs/memory-extraction-background);
    # routers schedule it as a background task and need the resolved LLM. Reuse the
    # single existing injection seam (llm=/fast_llm= override + get_agent_llm) by
    # attaching it to the compiled graph, alongside the already-exposed `.store`.
    compiled.extract_memory_llm = pick("extract_memory")
    # Panel-prose translation handle for the streaming layer — reuses the same
    # fast "extract_memory" seam so tests keep injecting FakeLLM offline.
    compiled.translate_llm = pick("extract_memory")
    return compiled


def resolve_travel_graph(app):
    """Return the compiled graph, rebuilding it if the config generation changed.

    Each node memoises its chat model for the compiled graph's life, so a DB
    config change (surfaced by ``AgentConfigCache``'s TTL refresh) only takes
    effect once the graph is rebuilt (MIN-47). The rebuild reuses the same
    process-lifetime checkpointer + store, so conversation state is preserved
    and no connection leaks.

    Falls back to serving the existing graph when it was never built, when the
    backends aren't stashed (e.g. a test that sets ``app.state.travel_graph``
    directly), or when a rebuild fails.

    :param app: The FastAPI app whose ``state`` holds the graph + backends.
    :return: The compiled travel-agent graph, or ``None`` if unavailable.
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
