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


def test_no_research_tool_asks_the_model_for_a_run_owned_id() -> None:
    """The run knows its trip and owner; the model does not. A tool that exposes
    ``trip_id``/``user_id`` as a model-supplied argument can only be answered with a
    guess — on the first live run a subagent invented ``trip_id="current"`` and the
    turn died on ``Trip 'current' not found``. Registry tools pass these through
    ``InjectedState``, which keeps them out of ``tool.args``.
    """
    from app.research.tools import _RUN_OWNED_IDS

    bound = {t.name: t for t in research_tools()}
    for tools in SUBAGENT_TOOLS.values():
        for tool in tools:
            bound[tool.name] = tool

    offenders = {
        name: sorted(_RUN_OWNED_IDS & set(tool.args))
        for name, tool in bound.items()
        if _RUN_OWNED_IDS & set(tool.args)
    }
    assert offenders == {}, offenders


def test_every_subagent_tool_obeys_the_parent_filter() -> None:
    """A subagent must not reach past the parent's pool: excluded or write tools are
    out of bounds however they are listed."""
    from app.research.tools import EXCLUDED
    from app.tools.registry import TOOL_METADATA

    for dimension, tools in SUBAGENT_TOOLS.items():
        for tool in tools:
            assert tool.name not in EXCLUDED, (dimension, tool.name)
            assert TOOL_METADATA[tool.name]["readOnly"], (dimension, tool.name)
