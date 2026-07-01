"""Travel agent graph assembly (specs/travel-agent Task 5.4).

Wires the full agentic graph:

    START -> load_context -> summarize -> supervisor
                                              | Command(goto=<sub-agent>)
                 planner / concierge / journal / booking / budget
                                              v
                                         reflection
                                   Command(goto=<sub-agent> | END)

The supervisor routes by intent; each sub-agent is a ReAct subgraph that
self-corrects on tool errors; reflection adds a bounded answer-quality loop.
Checkpointer + store make it stateful across turns/sessions.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore

from app.agents.context import AgentContext
from app.agents.nodes import (
    load_context_node,
    make_extract_memory_node,
    make_reflection_node,
    make_summarize_node,
    plan_node,
)
from app.agents.state import TravelAgentState
from app.agents.subagents.booking import build_booking
from app.agents.subagents.budget import build_budget
from app.agents.subagents.concierge import build_concierge
from app.agents.subagents.journal import build_journal
from app.agents.subagents.planner import build_planner
from app.agents.supervisor import SUBAGENTS, make_supervisor
from app.clients.llm import FAST_AGENTS, get_agent_llm


def build_graph(
    *,
    llm: BaseChatModel | None = None,
    fast_llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
):
    """Compile the travel agent graph. Inject fakes/backends for tests.

    Each node resolves its own model via ``get_agent_llm`` so providers/models
    can be tuned per agent (``settings.agent_llm_configs``). When tests inject
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
        ``ctx_model`` → all existing tests stay green. In prod,
        ``get_agent_llm(name, model=ctx_model)`` does per-request selection.

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
                cache[ctx_model] = get_agent_llm(name, model=ctx_model)
            return cache[ctx_model]

        return resolve

    builder = StateGraph(TravelAgentState, context_schema=AgentContext)
    builder.add_node("load_context", load_context_node)
    builder.add_node("summarize", make_summarize_node(pick("summarize")))
    builder.add_node(
        "supervisor",
        make_supervisor(pick("supervisor")),
        destinations=(*SUBAGENTS, "plan", "__end__"),
    )
    # HITL plan-approval gate: fires before booking commits anything destructive.
    builder.add_node("plan", plan_node, destinations=("booking", "__end__"))
    builder.add_node("planner", build_planner(resolver_for("planner")))
    builder.add_node("concierge", build_concierge(resolver_for("concierge")))
    builder.add_node("journal", build_journal(resolver_for("journal")))
    builder.add_node("booking", build_booking(resolver_for("booking")))
    builder.add_node("budget", build_budget(resolver_for("budget")))
    builder.add_node(
        "reflection",
        make_reflection_node(pick("reflection")),
        destinations=(*SUBAGENTS, "extract_memory"),
    )
    builder.add_node("extract_memory", make_extract_memory_node(pick("extract_memory")))

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "summarize")
    builder.add_edge("summarize", "supervisor")
    # supervisor -> sub-agent (or plan) is a Command(goto=...) handoff (no static edge).
    for name in SUBAGENTS:
        builder.add_edge(name, "reflection")
    # plan -> booking | END is a Command(goto=...) after interrupt resumes.
    # reflection -> sub-agent | extract_memory is a Command(goto=...).
    builder.add_edge("extract_memory", END)

    return builder.compile(checkpointer=checkpointer, store=store)
