#!/usr/bin/env python3
"""SC-6 check: the active prompts really carry the `list_trips` rule (gh-166).

`active.yaml` is a *pointer* — editing a `vN.md` without bumping it is a silent
no-op (``docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md``). So this
check does not read a file path: it resolves each agent's prompt through
``app.prompts.registry.get(name)``, which is the same resolution the running
agent uses, and asserts the returned text mentions ``list_trips``.

Only the agents that actually bind the tool are checked — the concierge holds no
trip tools and must not be told to call one
(``docs/solutions/agent/concierge-hotel-tool-choice.md``).

Run from ``apps/api/``::

    ../../.venv/bin/python scripts/check_gh166_prompt_wiring.py

Exits 0 when every checked prompt carries the rule, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `python scripts/foo.py` puts scripts/ on sys.path, not apps/api — make the
# `app` package importable so the script runs by path as well as by module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.prompts.registry import registry  # noqa: E402

# Agents that bind `list_trips` and therefore must carry the two-trigger rule.
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
