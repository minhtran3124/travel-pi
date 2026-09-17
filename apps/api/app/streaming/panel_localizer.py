"""Localize side-panel payloads to the traveller's language at emission time.

Registry-driven: ``vi`` dispatches to the registered panel kind's ``localize_vi``
and deep-copies first so the persisted checkpoint's English payload is never
mutated in place; ``en`` (and any non-``vi``) is an identity no-op.
"""

from __future__ import annotations

import copy

from app.core.languages import DEFAULT_LANGUAGE, normalize
from app.streaming.panels.base import get_panel


async def localize_panel(kind: str, data: dict, language: str) -> dict:
    """Localize a side-panel ``data`` dict to ``language``.

    ``en`` / any non-``vi`` (and a non-dict ``data``) returns the same object
    unmodified; ``vi`` deep-copies then dispatches to the kind's ``localize_vi``.
    """
    if normalize(language) == DEFAULT_LANGUAGE or not isinstance(data, dict):
        return data

    out = copy.deepcopy(data)

    spec = get_panel(kind)
    if spec is not None and spec.localize_vi is not None:
        await spec.localize_vi(out)

    return out
