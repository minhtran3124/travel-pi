"""Load + validate offline eval datasets (MIN-58, MIN-65)."""

from __future__ import annotations

import json
from pathlib import Path

_DATASETS = Path(__file__).resolve().parent / "datasets"
_REQUIRED = "input"


def _validate_case(name: str, i: int, case: dict) -> None:
    """Validate one case against either the single-turn or multi-turn shape.

    Single-turn (MIN-58): requires a string ``input``.
    Multi-turn (MIN-65 D9): requires a non-empty list of string ``turns``, and
    when present, ``new_thread_at`` must be an int strictly between 0 and
    ``len(turns)`` (it names the turn index that opens a new thread — index 0
    can't "open new" since it's already the first turn of the case).
    """
    if not isinstance(case, dict):
        raise ValueError(f"{name}[{i}]: case must be a JSON object")

    if "turns" in case:
        turns = case["turns"]
        if (
            not isinstance(turns, list)
            or not turns
            or not all(isinstance(t, str) for t in turns)
        ):
            raise ValueError(f"{name}[{i}]: 'turns' must be a non-empty list of strings")
        new_thread_at = case.get("new_thread_at")
        if new_thread_at is not None:
            valid = isinstance(new_thread_at, int) and not isinstance(new_thread_at, bool)
            if not valid or not (0 < new_thread_at < len(turns)):
                raise ValueError(
                    f"{name}[{i}]: 'new_thread_at' must be an int in (0, len(turns))"
                )
        return

    if _REQUIRED not in case or not isinstance(case[_REQUIRED], str):
        raise ValueError(f"{name}[{i}]: missing required string 'input'")


def load(name: str) -> list[dict]:
    """Load and validate one dataset file by name (e.g. ``intent.json``)."""
    data = json.loads((_DATASETS / name).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{name}: expected a JSON list")
    for i, case in enumerate(data):
        _validate_case(name, i, case)
    return data


def load_all() -> dict[str, list[dict]]:
    """Load every MIN-58/MIN-65 dataset (excludes routing.json — owned by run_eval)."""
    names = [
        "intent.json",
        "language.json",
        "tools.json",
        "format.json",
        "memory.json",
        "suggestions.json",
    ]
    return {n: load(n) for n in names}
