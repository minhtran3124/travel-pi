"""Load + validate offline eval datasets (MIN-58)."""

from __future__ import annotations

import json
from pathlib import Path

_DATASETS = Path(__file__).resolve().parent / "datasets"
_REQUIRED = "input"


def load(name: str) -> list[dict]:
    """Load and validate one dataset file by name (e.g. ``intent_min51.json``)."""
    data = json.loads((_DATASETS / name).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{name}: expected a JSON list")
    for i, case in enumerate(data):
        if _REQUIRED not in case or not isinstance(case[_REQUIRED], str):
            raise ValueError(f"{name}[{i}]: missing required string 'input'")
    return data


def load_all() -> dict[str, list[dict]]:
    """Load every MIN-58 dataset (excludes routing.json — owned by run_eval)."""
    names = [
        "intent_min51.json",
        "language_min57.json",
        "tools_min46.json",
        "format_min54.json",
    ]
    return {n: load(n) for n in names}
