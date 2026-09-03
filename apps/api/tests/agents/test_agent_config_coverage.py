"""Every node that resolves its own model must have an ``agent_config`` row.

A node whose name is missing from ``AGENT_CONFIG_NODES`` gets no seeded row, so
``get_agent_llm`` finds nothing in ``AgentConfigCache`` and silently falls back
to the env default model — the dashboard then cannot configure it and a turn can
mix models without anyone noticing (this is exactly how ``synthesize`` drifted).

The node names are *derived* here — from the compiled graph and from a source
scan of the ``get_agent_llm(...)`` / ``pick(...)`` call sites — rather than
hardcoded, so a future node that resolves its own model fails this test instead
of quietly inheriting the env default.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.data.agent_config import AGENT_CONFIG_NODES

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Names that legitimately have NO ``agent_config`` row.
#
# - ``synthesis_worker`` resolves the *specialist's* model at worker runtime
#   (``worker_resolve`` -> ``resolver_for(<specialist>)``), so its calls are
#   already covered by the specialists' own rows. A row of its own would be
#   dead config. Asserted explicitly below so this exclusion cannot rot.
# - the rest are pure-graph nodes that never call a model.
NO_CONFIG_ROW: frozenset[str] = frozenset(
    {
        "synthesis_worker",
        "pii_guardrail",
        "load_context",
        "plan",
        "route_tasks",
        "tools",
        "trip_guard",
    }
)

# ``get_agent_llm("name")`` / ``pick("name")`` with a string-literal node name.
# Non-literal call sites (e.g. ``pick(SYNTHESIZE_NODE)``) are covered by the
# compiled-graph derivation instead.
_CALL_RE = re.compile(
    r"""(?:get_agent_llm|pick)\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""
)


def _build_graph():
    from app.agents.graph import build_graph
    from app.clients.llm import FakeLLM

    return build_graph(llm=FakeLLM(responses=["x"]), fast_llm=FakeLLM(responses=["x"]))


def _graph_node_names() -> set[str]:
    """Node names of the compiled graph, minus LangGraph's own sentinels."""
    return {
        name for name in _build_graph().get_graph().nodes if not name.startswith("__")
    }


def _source_resolved_names() -> set[str]:
    """Node names passed as string literals to ``get_agent_llm`` / ``pick``."""
    found: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        found.update(_CALL_RE.findall(path.read_text(encoding="utf-8")))
    return found


def test_source_scan_finds_tool_resolved_node():
    """Guard the scan itself: ``date_resolution`` is resolved from a tool.

    It is not a graph node (``app/tools/date_tools.py`` calls ``get_agent_llm``
    directly), so only the source scan can see it. If this stops matching, the
    scan has silently stopped covering non-graph call sites.
    """
    assert "date_resolution" in _source_resolved_names()


def test_synthesis_worker_has_no_config_row_by_design():
    """It resolves the *specialist's* model, so it must stay row-less."""
    assert "synthesis_worker" in _graph_node_names()
    assert "synthesis_worker" not in AGENT_CONFIG_NODES, (
        "synthesis_worker must NOT have an agent_config row: it resolves the "
        "specialist's model via worker_resolve, so a row of its own would be "
        "dead config that silently does nothing."
    )


def test_excluded_names_have_no_config_row():
    """The exclusion list may not hide a node that actually has a row."""
    overlap = sorted(NO_CONFIG_ROW & set(AGENT_CONFIG_NODES))
    assert not overlap, (
        f"{overlap} are listed in NO_CONFIG_ROW but DO have an agent_config "
        "row. Remove them from NO_CONFIG_ROW in this test — the exclusion is "
        "stale and would mask a real coverage gap."
    )


def test_every_model_resolving_node_has_a_config_row():
    derived = (_graph_node_names() | _source_resolved_names()) - NO_CONFIG_ROW
    missing = sorted(derived - set(AGENT_CONFIG_NODES))
    assert not missing, (
        f"Node(s) {missing} resolve a model via get_agent_llm but have no "
        "agent_config row, so they silently fall back to the env default model "
        "and cannot be configured from the dashboard. Fix: add each name to a "
        "group in AGENT_CONFIG_GROUPS (app/data/agent_config.py) with an "
        "AGENT_DESCRIPTIONS entry — the seeder and the dashboard derive from "
        "that list. If a node deliberately has no row (like synthesis_worker, "
        "which resolves the specialist's model), add it to NO_CONFIG_ROW in "
        "this test with a comment saying why."
    )
