"""``panel_result`` registry-backed validation (specs/streaming-panels-split Task 2.2).

The two drift guards below are deliberately derived from the *source* — the tool
modules' ASTs and the files on disk in ``app/streaming/panels/`` — never from a
hand-maintained literal. A guard restated by hand is only a guard against the
mistakes you already thought of.
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
    """Every literal ``kind=`` passed to ``panel_result`` anywhere in ``app/tools/``.

    Parses the tool modules rather than importing them, so a tool that emits a
    kind is visible here whether or not anything registered that kind.

    :return: The set of panel kinds the real tools emit.
    """
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
    """The panel modules present in ``app/streaming/panels/`` (excluding infra).

    :return: Module stems, e.g. ``{"weather", "hotels", ...}``.
    """
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
    """The guard must not be catchable as a recoverable tool error.

    ``flight_tools`` / ``hotel_tools`` wrap ``ValueError`` and ``AppError`` into
    ``ToolException``, which the agent relays back to the model as a *logic* error —
    a mistyped kind would then reach the traveller as a chat message instead of
    failing loudly. If someone "helpfully" rebases ``UnknownPanelKind`` onto
    ``ValueError``, this fails.
    """
    from app.exceptions import AppError

    assert not issubclass(UnknownPanelKind, ValueError)
    assert not issubclass(UnknownPanelKind, AppError)


def test_every_kind_a_tool_emits_is_registered():
    """Drift guard, read from the tool modules' AST — not from a literal.

    Catches the copy-paste where a tool starts emitting a kind no panel module
    registers (an unrenderable panel ships to the FE), and the reverse: a panel
    module registered that no tool ever emits (dead panel).
    """
    emitted = _kinds_emitted_by_tools()
    registered = set(panel_kinds())
    assert emitted, "parsed zero panel_result(kind=...) calls — the AST scan broke"
    assert emitted == registered, (
        f"emitted by a tool but not registered (FE gets an unrenderable panel): "
        f"{emitted - registered}; "
        f"registered but no tool emits it (dead panel module): {registered - emitted}"
    )


def test_every_panel_module_is_imported_and_registered():
    """The failure mode import-time registration introduces.

    A panel module that ``panels/__init__.py`` never imports is never registered —
    ``panel_kinds()`` silently omits it and every registry-keyed test stays green
    while the tool fails in production. Compare against the files on disk, which is
    the one source the registry cannot lie about.
    """
    on_disk = _panel_modules_on_disk()
    registered = set(panel_kinds())
    assert on_disk == registered, (
        f"module file exists but its kind is not registered — most likely missing "
        f"from the imports in panels/__init__.py: {on_disk - registered}; "
        f"kind registered with no module file of that name: {registered - on_disk}"
    )
