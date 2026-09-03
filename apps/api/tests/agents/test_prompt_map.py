"""Prompt attribution map (specs/agent-run-trace-detail §4.2, SC-4).

The expected node-key set is DERIVED from the compiled graph rather than
hardcoded, so adding or renaming a node fails these tests instead of silently
producing steps with no attribution.
"""

from __future__ import annotations

import pytest
from app.agents.constants import ALL_SUBAGENTS
from app.agents.graph import build_graph
from app.agents.metrics import _node_key
from app.agents.prompt_map import (
    PROMPTS_FOR_NODE,
    prompt_versions_snapshot,
    prompts_for,
)
from app.clients.llm import FakeLLM
from app.prompts.registry import registry

# Inner sub-graph nodes are re-run by ``synthesis_worker`` under its own
# checkpoint namespace, so the worker contributes the same inner keys.
_SUBGRAPH_HOSTS = (*ALL_SUBAGENTS, "synthesis_worker")


@pytest.fixture(scope="module")
def graph():
    return build_graph(llm=FakeLLM(), fast_llm=FakeLLM())


def _derived_node_keys(graph) -> set[str]:
    """Every ``_node_key`` the compiled graph can produce.

    Top-level nodes key on their bare name; a node wrapping a compiled
    sub-graph also produces ``"<node>/<inner>"`` for each of its inner nodes
    (that is what ``_node_key`` renders from the checkpoint namespace).
    LangGraph's own ``__``-prefixed nodes (``__start__``, error handlers) are
    infrastructure, not agent steps, and are excluded.
    """
    keys: set[str] = set()
    inner_names: set[str] = set()
    for name, node in graph.nodes.items():
        if name.startswith("__"):
            continue
        keys.add(name)
        sub = getattr(node, "bound", None)
        for inner in getattr(sub, "nodes", {}) or {}:
            if inner.startswith("__"):
                continue
            inner_names.add(inner)
            keys.add(f"{name}/{inner}")
    # The parallel synthesis worker invokes a sub-agent sub-graph inside its own
    # node, so those inner nodes appear under the worker's namespace root too.
    keys.update(f"synthesis_worker/{inner}" for inner in inner_names)
    return keys


def test_map_covers_exactly_the_graphs_node_keys(graph):
    assert set(PROMPTS_FOR_NODE) == _derived_node_keys(graph)


def test_derived_keys_are_the_node_key_form(graph):
    # The sub-graph keys must match what the metrics handler actually emits.
    assert _node_key("assistant", "planner:abc|assistant:def") == "planner/assistant"
    assert _node_key("supervisor", "") == "supervisor"
    for key in _derived_node_keys(graph):
        assert key.count("/") <= 1


def test_subagents_are_distinct_and_do_not_collapse_onto_assistant():
    keys = [f"{name}/assistant" for name in ALL_SUBAGENTS]
    assert len(set(keys)) == len(ALL_SUBAGENTS) == 5
    assert "assistant" not in PROMPTS_FOR_NODE
    listed = [tuple(PROMPTS_FOR_NODE[k]) for k in keys]
    assert len(set(listed)) == len(ALL_SUBAGENTS)
    for name, key in zip(ALL_SUBAGENTS, keys, strict=True):
        assert PROMPTS_FOR_NODE[key] == [name, "communication_style"]


def test_root_prompt_nodes():
    assert PROMPTS_FOR_NODE["supervisor"] == ["supervisor"]
    assert PROMPTS_FOR_NODE["reflection"] == ["reflection"]


@pytest.mark.parametrize(
    "node_key",
    [
        "pii_guardrail",
        "load_context",
        "plan",
        "summarize",
        "synthesize",
        "synthesis_worker",
        "synthesis_worker/assistant",
        "planner/tools",
        "planner/trip_guard",
    ],
)
def test_promptless_nodes_map_to_empty(node_key):
    assert PROMPTS_FOR_NODE[node_key] == []
    assert prompts_for(node_key, prompt_versions_snapshot(registry)) == []


def test_every_mapped_prompt_name_is_registered():
    names = set(registry.names())
    for prompts in PROMPTS_FOR_NODE.values():
        assert set(prompts) <= names


def test_snapshot_covers_every_registry_name():
    snapshot = prompt_versions_snapshot(registry)
    assert set(snapshot) == set(registry.names())
    assert snapshot  # the registry is not empty
    for name, version in snapshot.items():
        assert version == registry.active_version(name)
        assert isinstance(version, int)


def test_prompts_for_returns_name_version_pointers():
    snapshot = prompt_versions_snapshot(registry)
    assert prompts_for("concierge/assistant", snapshot) == [
        {"name": "concierge", "version": snapshot["concierge"]},
        {"name": "communication_style", "version": snapshot["communication_style"]},
    ]


def test_prompts_for_unknown_node_is_empty():
    assert prompts_for("does_not_exist", prompt_versions_snapshot(registry)) == []


def test_map_values_are_independent_lists():
    PROMPTS_FOR_NODE["planner"].append("bogus")
    try:
        assert PROMPTS_FOR_NODE["planner/assistant"] == [
            "planner",
            "communication_style",
        ]
    finally:
        PROMPTS_FOR_NODE["planner"].remove("bogus")
