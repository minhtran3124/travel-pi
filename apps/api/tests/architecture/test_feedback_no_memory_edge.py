"""No import edge from the feedback write path to the memory runner/store (SC-9).

DESIGN §10 (specs/user-feedback-v1): feedback must never change memory. This
walks the static import graph of the feedback service and router and fails if
any module under ``app.memory`` is reachable. ``app.agents.memory`` does not
exist in this repo (``ls app/agents``); ``app.memory`` is the runner + store.
"""

import ast
import importlib.util
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
ROOTS = ["app.services.feedback_service", "app.routers.feedback"]
FORBIDDEN_PREFIXES = ("app.memory", "app.agents.memory")


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
    """Return the ``app.*`` modules this module imports (static, no execution)."""
    path = _module_path(name)
    if path is None:
        return set()
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names if a.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app"):
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
