"""resolve_travel_graph — rebuild the compiled graph when config changes (MIN-47).

The graph memoises each node's chat model for its lifetime, so a DB config
change only takes effect once the graph is rebuilt. resolve_travel_graph gates
that rebuild on the AgentConfigCache generation counter.
"""

from types import SimpleNamespace

import app.agents.graph as graphmod


def _app(**state):
    return SimpleNamespace(state=SimpleNamespace(**state))


def test_rebuilds_only_when_generation_changes(monkeypatch):
    built = []

    def fake_build_graph(**kwargs):
        built.append(kwargs)
        return f"graph-{len(built)}"

    monkeypatch.setattr(graphmod, "build_graph", fake_build_graph)
    gen = {"v": 5}
    monkeypatch.setattr(graphmod.AgentConfigCache, "generation", lambda: gen["v"])

    app = _app(
        travel_graph="graph-0",
        travel_graph_gen=5,
        agent_checkpointer="CP",
        agent_store="ST",
    )

    # Same generation → serve the existing graph, no rebuild.
    assert graphmod.resolve_travel_graph(app) == "graph-0"
    assert built == []

    # Generation changed → rebuild, reusing the same checkpointer + store.
    gen["v"] = 6
    assert graphmod.resolve_travel_graph(app) == "graph-1"
    assert built == [{"checkpointer": "CP", "store": "ST"}]
    assert app.state.travel_graph_gen == 6

    # Stable again at the new generation → no further rebuild.
    assert graphmod.resolve_travel_graph(app) == "graph-1"
    assert len(built) == 1


def test_serves_as_is_without_stashed_backends(monkeypatch):
    # A test/app that puts a graph on state without checkpointer/store (e.g. a
    # FakeLLM-injected graph) must never trigger a rebuild.
    built = []
    monkeypatch.setattr(graphmod, "build_graph", lambda **k: built.append(k))

    app = _app(travel_graph="injected")
    assert graphmod.resolve_travel_graph(app) == "injected"
    assert built == []


def test_none_when_graph_never_built():
    assert graphmod.resolve_travel_graph(_app()) is None
    assert graphmod.resolve_travel_graph(_app(travel_graph=None)) is None
