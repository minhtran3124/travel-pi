"""The portability gate (agent-eval-pipeline task 1.1).

`evalkit/` must be extractable as a standalone package: it may never import
this repo's `app.*`, nor depend on fastapi/sqlalchemy/langgraph/langchain.
This walks every module under `evalkit/` with `ast` (no import execution
needed) and fails loud, with file + offending module name, on a violation.
"""

from __future__ import annotations

import ast
from pathlib import Path

EVALKIT_ROOT = Path(__file__).resolve().parents[2] / "evalkit"
BANNED_MODULES = {"app", "fastapi", "sqlalchemy", "langgraph", "langchain"}


def find_banned_imports(source: str) -> list[str]:
    """Return the banned top-level module names imported by *source*."""
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in BANNED_MODULES:
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in BANNED_MODULES:
                violations.append(node.module)
    return violations


def test_detector_flags_a_banned_import():
    """Sanity: the detector itself must catch a violation, or the gate below
    is a no-op that would pass even with a leaked `app.*`/fastapi import.
    """
    source = "import app.services.trip_service\nfrom fastapi import FastAPI\n"
    violations = find_banned_imports(source)
    assert violations == ["app.services.trip_service", "fastapi"]


def test_evalkit_has_zero_app_or_framework_imports():
    py_files = sorted(EVALKIT_ROOT.rglob("*.py"))
    assert py_files, f"expected .py files under {EVALKIT_ROOT}"

    offenders: dict[str, list[str]] = {}
    for path in py_files:
        violations = find_banned_imports(path.read_text(encoding="utf-8"))
        if violations:
            offenders[str(path.relative_to(EVALKIT_ROOT))] = violations

    assert not offenders, f"evalkit/ must stay portable — banned imports: {offenders}"
