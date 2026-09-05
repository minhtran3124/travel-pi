"""The compiled graph no longer carries a panel-prose translator handle.

Free-form panel text is localized at tool time from the ``content_translations``
store (specs/catalog-content-i18n); the SSE path makes no LLM call for panels.
"""

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
