"""The compiled graph carries a build-time ``prompt_versions`` snapshot, not the turn-time ``active.yaml`` values."""

from app.agents.graph import build_graph
from app.clients.llm import FakeLLM
from app.prompts.registry import registry
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _graph():
    return build_graph(
        llm=FakeLLM(responses=["ok"]),
        fast_llm=FakeLLM(responses=["ok"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )


def test_compiled_graph_exposes_active_versions_for_every_prompt():
    snapshot = _graph().prompt_versions

    assert isinstance(snapshot, dict)
    assert set(snapshot) == set(registry.names())
    assert snapshot
    assert snapshot == {
        name: registry.active_version(name) for name in registry.names()
    }
    assert all(isinstance(v, int) for v in snapshot.values())


def test_snapshot_is_taken_at_build_not_read_per_turn(monkeypatch):
    graph = _graph()
    before = dict(graph.prompt_versions)

    # A later registry change must not retro-alter what the graph recorded.
    monkeypatch.setattr(registry, "active_version", lambda name: 999, raising=True)
    assert graph.prompt_versions == before
