"""Guard: services/routers hold no module-level repo/service singletons or
``set_*_repo`` mutators — every DB dependency resolves per request via
``Depends(get_session)`` (specs/di-session-refactor success criterion #2).
"""

import re
from pathlib import Path

_ROOTS = [
    Path(__file__).resolve().parents[2] / "app" / "services",
    Path(__file__).resolve().parents[2] / "app" / "routers",
]

# Module-level `_x_repo = ...` / `_x_service = ...` (import-time singletons) and
# any `set_*_repo` mutator are the patterns the refactor removed.
_SINGLETON = re.compile(r"^_\w*(?:_repo|_service)\s*=", re.MULTILINE)
_SETTER = re.compile(r"def\s+set_\w*_repo\b|def\s+set_repos\b")


def _py_files() -> list[Path]:
    return [p for root in _ROOTS for p in root.rglob("*.py")]


def test_no_module_level_repo_or_service_singletons() -> None:
    offenders = []
    for path in _py_files():
        text = path.read_text()
        if _SINGLETON.search(text):
            offenders.append(path.name)
    assert not offenders, (
        f"Module-level repo/service singletons found in: {offenders}. "
        "Resolve repos per request via Depends(get_session) instead."
    )


def test_no_set_repo_mutators() -> None:
    offenders = []
    for path in _py_files():
        if _SETTER.search(path.read_text()):
            offenders.append(path.name)
    assert not offenders, (
        f"set_*_repo / set_repos mutators found in: {offenders}. "
        "These were replaced by request-scoped DI; do not reintroduce them."
    )
