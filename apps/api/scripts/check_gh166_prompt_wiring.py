#!/usr/bin/env python3
"""Check that the active prompts carry the `list_trips` rule.

``active.yaml`` is a pointer, so this resolves each agent's prompt through the
registry (the same resolution the running agent uses) rather than reading a file.

Run from ``apps/api/``: ``../../.venv/bin/python scripts/check_gh166_prompt_wiring.py``
(exits 0 when every checked prompt carries the rule, 1 otherwise).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `app` package importable when run by path, not only as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.prompts.registry import registry  # noqa: E402

# Only agents that bind `list_trips` must carry the rule.
AGENTS = ("planner", "journal")
TOKEN = "list_trips"


def check() -> list[str]:
    """Return a failure message per agent whose active prompt lacks the rule."""
    failures: list[str] = []
    for name in AGENTS:
        version = registry.active_version(name)
        text = registry.get(name)
        if TOKEN not in text:
            failures.append(
                f"{name}: active.yaml resolves to v{version}, whose text does not "
                f"mention {TOKEN!r} — the pointer misses the file carrying the rule."
            )
        else:
            print(f"ok  {name}: active v{version} mentions {TOKEN!r}")
    return failures


def main() -> int:
    """Print the per-agent result and return the process exit code."""
    failures = check()
    for message in failures:
        print(f"FAIL {message}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
