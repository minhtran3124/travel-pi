"""Localize side-panel payloads to the traveller's language at emission time.

Side-panel ``data`` dicts (see ``app/streaming/panels/``) carry English
strings baked in by the panel projections. Dispatch is registry-driven: when
the conversation language is ``vi``, the registered panel's ``localize_vi``
callable (see ``app.streaming.panels.base.PanelSpec``) swaps the *bounded*
strings for that kind. Each kind's ``vi`` lookup tables live next to the
panel they translate, in its own module under ``app/streaming/panels/`` — no
table and no ``if kind == ...`` dispatch chain live in this module.

``en`` (and any non-``vi`` language) is a strict identity no-op: the same
object is returned, unmodified and un-copied. ``vi`` deep-copies first so the
persisted checkpoint's English payload is never mutated in place.
"""

from __future__ import annotations

import copy

from app.streaming.panels.base import Translator, get_panel


async def localize_panel(
    kind: str,
    data: dict,
    language: str,
    translator: Translator | None = None,
) -> dict:
    """Localize a side-panel ``data`` dict to ``language``.

    ``en`` / any non-``vi`` language (and a non-dict ``data``) is an identity
    no-op — the SAME object is returned, unmodified. ``vi`` deep-copies
    ``data`` then dispatches to the registered panel kind's ``localize_vi``,
    if any; an unregistered kind, or one with no localizer, copies but
    localizes nothing.

    :param kind: The panel kind (``weather`` / ``air_quality`` / ``places`` /
        ``hotels`` / ...); kinds with no bounded strings copy but localize
        nothing.
    :param data: The panel ``data`` projection to localize.
    :param language: The conversation language (only ``vi`` triggers work).
    :param translator: Callable used to translate free-form prose; only
        consulted by kinds that accept it (currently ``places``). Never
        falls back to an LLM here — an absent translator leaves the English
        text in place.
    :return: The (possibly localized) panel data.
    """
    if language != "vi" or not isinstance(data, dict):
        return data

    out = copy.deepcopy(data)

    spec = get_panel(kind)
    if spec is not None and spec.localize_vi is not None:
        await spec.localize_vi(out, translator)

    return out
