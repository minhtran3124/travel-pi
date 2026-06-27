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

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.store.base import BaseStore

from app.agents.nodes import (
    load_context_node,
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
    """

    def pick(name: str) -> BaseChatModel:
        if name in FAST_AGENTS:
            return fast_llm if fast_llm is not None else get_agent_llm(name)
        return llm if llm is not None else get_agent_llm(name)

    builder = StateGraph(TravelAgentState)
    builder.add_node("load_context", load_context_node)
    builder.add_node("summarize", make_summarize_node(pick("summarize")))
    builder.add_node(
        "supervisor",
        make_supervisor(pick("supervisor")),
        destinations=(*SUBAGENTS, "plan", "__end__"),
    )
    # HITL plan-approval gate: fires before booking commits anything destructive.
    builder.add_node("plan", plan_node, destinations=("booking", "__end__"))
    builder.add_node("planner", build_planner(pick("planner")))
    builder.add_node("concierge", build_concierge(pick("concierge")))
    builder.add_node("journal", build_journal(pick("journal")))
    builder.add_node("booking", build_booking(pick("booking")))
    builder.add_node("budget", build_budget(pick("budget")))
    builder.add_node(
        "reflection",
        make_reflection_node(pick("reflection")),
        destinations=(*SUBAGENTS, "__end__"),
    )

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "summarize")
    builder.add_edge("summarize", "supervisor")
    # supervisor -> sub-agent (or plan) is a Command(goto=...) handoff (no static edge).
    for name in SUBAGENTS:
        builder.add_edge(name, "reflection")
    # plan -> booking | END is a Command(goto=...) after interrupt resumes.
    # reflection -> sub-agent | END is a Command(goto=...).

    return builder.compile(checkpointer=checkpointer, store=store)
