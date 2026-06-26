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
)
from app.agents.state import TravelAgentState
from app.agents.subagents.booking import build_booking
from app.agents.subagents.budget import build_budget
from app.agents.subagents.concierge import build_concierge
from app.agents.subagents.journal import build_journal
from app.agents.subagents.planner import build_planner
from app.agents.supervisor import SUBAGENTS, make_supervisor
from app.clients.llm import get_fast_llm, get_llm


def build_graph(
    *,
    llm: BaseChatModel | None = None,
    fast_llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
):
    """Compile the travel agent graph. Inject fakes/backends for tests."""
    llm = llm or get_llm()
    fast_llm = fast_llm or get_fast_llm()

    builder = StateGraph(TravelAgentState)
    builder.add_node("load_context", load_context_node)
    builder.add_node("summarize", make_summarize_node(fast_llm))
    builder.add_node(
        "supervisor", make_supervisor(llm), destinations=(*SUBAGENTS, "__end__")
    )
    builder.add_node("planner", build_planner(llm))
    builder.add_node("concierge", build_concierge(llm))
    builder.add_node("journal", build_journal(fast_llm))
    builder.add_node("booking", build_booking(llm))
    builder.add_node("budget", build_budget(fast_llm))
    builder.add_node(
        "reflection",
        make_reflection_node(fast_llm),
        destinations=(*SUBAGENTS, "__end__"),
    )

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "summarize")
    builder.add_edge("summarize", "supervisor")
    # supervisor -> sub-agent is a Command(goto=...) handoff (no static edge).
    for name in SUBAGENTS:
        builder.add_edge(name, "reflection")
    # reflection -> sub-agent | END is a Command(goto=...).

    return builder.compile(checkpointer=checkpointer, store=store)
