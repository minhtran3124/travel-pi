"""File-backed, versioned prompt registry (specs/travel-agent Task 1.2).

Prompts live as flat markdown files named ``<name>.v<N>.md`` under this package.
``active.yaml`` declares which version is the production default per name. The
registry walks the directory once at import, loads every version into memory,
and ``get(name)`` returns the active version's text (override with ``version=``).

Zero runtime DB; hot-reload via ``registry.reload()``. Pattern adapted from the
chat-agents reference repo.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parent
_ACTIVE_FILE = _PROMPTS_DIR / "active.yaml"
_FILENAME_RE = re.compile(r"^(?P<name>.+)\.v(?P<version>\d+)\.md$")


class PromptRegistry:
    """In-memory store of ``{name: {version: text}}`` + active-version map."""

    def __init__(self, prompts_dir: Path = _PROMPTS_DIR) -> None:
        self._dir = prompts_dir
        self._prompts: dict[str, dict[int, str]] = {}
        self._active: dict[str, int] = {}
        self.reload()

    def reload(self) -> None:
        """Re-scan the directory and re-read ``active.yaml`` from disk."""
        self._prompts = {}
        for path in sorted(self._dir.glob("*.md")):
            m = _FILENAME_RE.match(path.name)
            if not m:
                continue
            name = m.group("name")
            version = int(m.group("version"))
            self._prompts.setdefault(name, {})[version] = path.read_text(
                encoding="utf-8"
            )
        active_file = self._dir / "active.yaml"
        self._active = (
            yaml.safe_load(active_file.read_text(encoding="utf-8")) or {}
            if active_file.exists()
            else {}
        )

    def get(self, name: str, version: int | None = None) -> str:
        """Return prompt text. Defaults to the active version for ``name``."""
        if name not in self._prompts:
            raise KeyError(f"Unknown prompt: {name!r}")
        versions = self._prompts[name]
        if version is None:
            version = self._active.get(name)
            if version is None:
                version = max(versions)  # newest if no active declared
        if version not in versions:
            raise KeyError(f"Prompt {name!r} has no version v{version}")
        return versions[version]

    def names(self) -> list[str]:
        """All known prompt names."""
        return sorted(self._prompts)


# Module-level singleton — import and call registry.get(...).
registry = PromptRegistry()
