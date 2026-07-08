"""The compiled graph exposes a fast translate LLM handle for the streaming layer."""

from app.agents.graph import build_graph
from app.clients.llm import FakeLLM
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def test_graph_exposes_translate_llm():
    graph = build_graph(
        llm=FakeLLM(responses=["ok"]),
        fast_llm=FakeLLM(responses=["ok"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    assert getattr(graph, "translate_llm", None) is not None
