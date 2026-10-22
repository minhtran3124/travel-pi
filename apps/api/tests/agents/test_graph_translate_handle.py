"""The compiled graph carries no panel-prose translator handle; panels are localized at tool time, not via an LLM call."""

from app.agents.graph import build_graph
from app.clients.llm import FakeLLM
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def test_graph_has_no_translate_llm_handle():
    graph = build_graph(
        llm=FakeLLM(responses=["ok"]),
        fast_llm=FakeLLM(responses=["ok"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    assert not hasattr(graph, "translate_llm")
    assert graph.extract_memory_llm is not None
