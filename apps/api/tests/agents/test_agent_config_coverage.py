"""Every model-resolving node must have an ``agent_config`` row, else it silently falls back to the env default and cannot be configured from the dashboard."""

from __future__ import annotations

import re
from pathlib import Path

from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.seed import _RESEARCH_AGENT_MIRRORS

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# The research agent's nodes resolve a model but are seeded through
# ``_seed_research_agent_config`` (seed.py), not ``AGENT_CONFIG_GROUPS``. They DO
# get a concrete config row, so the coverage check counts them as covered.
_RESEARCH_SEEDED: frozenset[str] = frozenset(
    name for name, _sibling, _fast in _RESEARCH_AGENT_MIRRORS
)
CONFIGURED_NODES: frozenset[str] = frozenset(AGENT_CONFIG_NODES) | _RESEARCH_SEEDED

# Names that legitimately have NO ``agent_config`` row: synthesis_worker
# resolves the specialist's model at runtime; the rest never call a model.
NO_CONFIG_ROW: frozenset[str] = frozenset(
    {
        "synthesis_worker",
        "pii_guardrail",
        "load_context",
        "plan",
        "route_tasks",
        "tools",
        "trip_guard",
        # The research launcher (app.research.launcher) books a background run and
        # makes no model call, so it resolves no agent_config model of its own.
        "research",
    }
)

# ``get_agent_llm("name")`` / ``pick("name")`` with a string-literal node name.
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
    """``date_resolution`` is resolved from a tool, not a graph node, so only the source scan can see it."""
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
    missing = sorted(derived - CONFIGURED_NODES)
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
