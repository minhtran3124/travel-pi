"""The compiled graph carries its build-time prompt snapshot (SC-5).

``prompt_versions`` is evaluated inside ``build_graph`` and attached to the
compiled graph, so it records the versions the running graph baked in rather
than whatever ``active.yaml`` says at turn time.
"""

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
    assert snapshot  # the registry is non-empty
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
