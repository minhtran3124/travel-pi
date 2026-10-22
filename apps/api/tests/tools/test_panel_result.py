"""``panel_result`` registry-backed validation.

The drift guards are derived from source (tool ASTs and files on disk), never a
hand-maintained literal, which would only guard against mistakes already foreseen.
"""

import ast
import pathlib

import pytest
from app.streaming.panels import UnknownPanelKind, panel_kinds
from app.tools._base import panel_result

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"
_TOOLS_DIR = _APP / "tools"
_PANELS_DIR = _APP / "streaming" / "panels"


def _kinds_emitted_by_tools() -> set[str]:
    """Panel kinds the real tools emit, parsed (not imported) from ``app/tools/``."""
    kinds: set[str] = set()
    for path in _TOOLS_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            )
            if name != "panel_result":
                continue
            for kw in node.keywords:
                if kw.arg == "kind" and isinstance(kw.value, ast.Constant):
                    kinds.add(kw.value.value)
    return kinds


def _panel_modules_on_disk() -> set[str]:
    """The panel module stems present in ``app/streaming/panels/`` (excluding infra)."""
    return {
        p.stem for p in _PANELS_DIR.glob("*.py") if p.stem not in {"__init__", "base"}
    }


@pytest.mark.parametrize("kind", panel_kinds())
def test_panel_result_round_trips_registered_kind(kind):
    summary, artifact = panel_result("s", kind=kind, data={})
    assert summary == "s"
    assert artifact == {"kind": kind, "data": {}}


def test_panel_result_rejects_unregistered_kind():
    with pytest.raises(UnknownPanelKind, match="unknown panel kind"):
        panel_result("s", kind="not_a_real_kind", data={})


def test_unknown_kind_is_not_swallowed_by_the_tool_error_handlers():
    """The guard must not be catchable as a recoverable tool error, or a mistyped kind reaches the traveller instead of failing loudly."""
    from app.exceptions import AppError

    assert not issubclass(UnknownPanelKind, ValueError)
    assert not issubclass(UnknownPanelKind, AppError)


def test_every_kind_a_tool_emits_is_registered():
    """Drift guard: a tool emitting an unregistered kind (unrenderable panel), or a registered kind no tool emits (dead panel)."""
    emitted = _kinds_emitted_by_tools()
    registered = set(panel_kinds())
    assert emitted, "parsed zero panel_result(kind=...) calls — the AST scan broke"
    assert emitted == registered, (
        f"emitted by a tool but not registered (FE gets an unrenderable panel): "
        f"{emitted - registered}; "
        f"registered but no tool emits it (dead panel module): {registered - emitted}"
    )


def test_every_panel_module_is_imported_and_registered():
    """A panel module ``panels/__init__.py`` never imports is never registered, so compare against files on disk."""
    on_disk = _panel_modules_on_disk()
    registered = set(panel_kinds())
    assert on_disk == registered, (
        f"module file exists but its kind is not registered — most likely missing "
        f"from the imports in panels/__init__.py: {on_disk - registered}; "
        f"kind registered with no module file of that name: {registered - on_disk}"
    )
