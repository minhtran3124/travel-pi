"""SC-2 tool selection: research_tools() is registry read-only tools minus the
excluded set, and every SUBAGENT_TOOLS name resolves against the registry."""

from __future__ import annotations

from app.research.tools import EXCLUDED, SUBAGENT_TOOLS, research_tools
from app.tools.registry import ALL_TOOLS, TOOL_METADATA


def test_research_tools_are_read_only() -> None:
    for tool in research_tools():
        assert TOOL_METADATA[tool.name]["readOnly"] is True


def test_research_tools_exclude_named() -> None:
    names = {t.name for t in research_tools()}
    assert names.isdisjoint(EXCLUDED)
    for excluded in (
        "list_trips",
        "recall_past_trips",
        "get_user_preferences",
        "parse_nl_query",
    ):
        assert excluded not in names


def test_research_tools_deduplicated() -> None:
    names = [t.name for t in research_tools()]
    assert len(names) == len(set(names))


def test_subagent_tools_resolve_in_registry() -> None:
    registry = {t.name for t in ALL_TOOLS}
    for group in SUBAGENT_TOOLS.values():
        for tool in group:
            assert tool.name in registry


def test_subagent_tools_are_read_only() -> None:
    for group in SUBAGENT_TOOLS.values():
        for tool in group:
            assert TOOL_METADATA[tool.name]["readOnly"] is True
