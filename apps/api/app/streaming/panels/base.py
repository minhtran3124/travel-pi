"""Panel registry: kind -> localizer lookup, and the set of valid kinds.

Nothing panel-specific lives here. Each panel module registers itself at
import time via :func:`register_panel`; :mod:`app.streaming.panels` imports
every submodule so registration actually happens.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Localizer = Callable[[dict], Awaitable[None]]


class UnknownPanelKind(Exception):
    """A panel kind that no module registered — a source-level bug, not a runtime condition.

    Deliberately NOT a ``ValueError`` and NOT an ``AppError``: the panel tools wrap
    both of those into ``ToolException``, which the agent relays back to the model as
    a recoverable *logic* error. A mistyped kind would then surface to the traveller as
    a chat message instead of failing loudly, so this must be a type neither handler
    catches. CI is the real guard (``tests/tools/test_panel_result.py`` scans the tool
    modules); this is the backstop.
    """


@dataclass(frozen=True)
class PanelSpec:
    kind: str
    localize_vi: Localizer | None = None


_REGISTRY: dict[str, PanelSpec] = {}


def register_panel(spec: PanelSpec) -> None:
    """Register a panel kind. Raises on a duplicate ``kind`` (re-registration is a bug).

    :param spec: The panel spec to register.
    :raises ValueError: If ``spec.kind`` is already registered.
    """
    if spec.kind in _REGISTRY:
        raise ValueError(f"panel kind already registered: {spec.kind!r}")
    _REGISTRY[spec.kind] = spec


def get_panel(kind: str) -> PanelSpec | None:
    """Look up a registered panel spec by kind.

    :param kind: The panel kind to look up.
    :return: The registered spec, or ``None`` if ``kind`` is not registered.
    """
    return _REGISTRY.get(kind)


def panel_kinds() -> tuple[str, ...]:
    """The registered panel kinds.

    :return: A tuple of every registered kind.
    """
    return tuple(_REGISTRY.keys())


def _swap(value: Any, table: dict[str, str]) -> Any:
    """Return ``table[value]`` when ``value`` is a mapped string, else ``value``.

    :param value: The candidate value (only ``str`` values are looked up).
    :param table: The English → Vietnamese lookup table.
    :return: The localized string, or the original value untouched.
    """
    if isinstance(value, str):
        return table.get(value, value)
    return value
