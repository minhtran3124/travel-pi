"""No import edge from the feedback write path to the memory runner/store (SC-9).

DESIGN §10 (specs/user-feedback-v1): feedback must never change memory. This
walks the static import graph of the feedback service and router and fails if
any forbidden module is reachable.

Surfaces covered (``FORBIDDEN_PREFIXES``):

- ``app.memory`` — the in-repo memory package: ``app.memory.store`` (the
  LangGraph store wrapper: ``open_store`` / ``get_store`` / ``upsert_*``),
  ``app.memory.extractor``, ``app.memory.extraction_runner``,
  ``app.memory.summarizer``.
- ``langgraph.store`` — the third-party store package the app imports
  directly (``langgraph.store.base.BaseStore``, ``langgraph.store.memory``,
  ``langgraph.store.postgres``; see ``rg "langgraph.store" app``). A feedback
  module that bypassed ``app.memory`` and opened the store itself is caught
  here.
- ``app.agents.memory`` — kept for forward compatibility; it does not exist in
  this repo today (``ls app/agents``).

The walker follows ``app.*`` imports transitively and records any import whose
name starts with a forbidden prefix, first-party or third-party; other
third-party modules are not walked.
"""

import ast
import importlib.util
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
ROOTS = ["app.services.feedback_service", "app.routers.feedback"]
FORBIDDEN_PREFIXES = ("app.memory", "app.agents.memory", "langgraph.store")


def _tracked(name: str) -> bool:
    """Follow ``app.*`` edges and record forbidden third-party ones."""
    return name.startswith("app.") or name.startswith(FORBIDDEN_PREFIXES)


def _find_spec(name: str):
    try:
        return importlib.util.find_spec(name)
    except (ModuleNotFoundError, ValueError):
        return None  # parent is a module, not a package


def _module_path(name: str) -> Path | None:
    spec = _find_spec(name)
    if spec is None or spec.origin is None or not spec.origin.endswith(".py"):
        return None
    return Path(spec.origin)


def _imports_of(name: str) -> set[str]:
    """Return the tracked modules this module imports (static, no execution).

    Tracked = every ``app.*`` module plus any module under a forbidden prefix
    (so a direct third-party ``langgraph.store`` import is recorded too).
    """
    path = _module_path(name)
    if path is None:
        return set()
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names if _tracked(a.name))
        elif isinstance(node, ast.ImportFrom) and _tracked(node.module or ""):
            out.add(node.module)
            # ``from app.pkg import mod`` may name a submodule.
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if _find_spec(candidate) is not None:
                    out.add(candidate)
    return out


def _reachable(roots: list[str]) -> dict[str, str]:
    """Walk imports transitively; return ``{module: imported_by}``."""
    seen: dict[str, str] = {}
    stack = [(root, "<root>") for root in roots]
    while stack:
        name, parent = stack.pop()
        if name in seen:
            continue
        seen[name] = parent
        stack.extend((dep, name) for dep in _imports_of(name))
    return seen


def test_feedback_path_does_not_reach_memory():
    reachable = _reachable(ROOTS)
    offenders = {
        mod: via for mod, via in reachable.items() if mod.startswith(FORBIDDEN_PREFIXES)
    }
    assert not offenders, f"feedback path reaches memory modules: {offenders}"
    # Sanity: the walk actually saw the repositories the service depends on.
    assert "app.repositories.feedback" in reachable


def test_walker_detects_memory_when_present():
    """Guard against a hollow gate: the memory package is reachable from the graph."""
    assert any(m.startswith("app.memory") for m in _reachable(["app.agents.graph"]))


def test_walker_records_direct_langgraph_store_imports():
    """The third-party store surface is recorded, not skipped as third-party."""
    direct = _imports_of("app.memory.store")
    assert any(m.startswith("langgraph.store") for m in direct), direct
    reachable = _reachable(["app.agents.graph"])
    assert any(m.startswith("langgraph.store") for m in reachable)
