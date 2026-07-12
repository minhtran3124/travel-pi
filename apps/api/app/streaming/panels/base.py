"""Panel registry: kind -> (model, localizer) lookup.

Nothing panel-specific lives here. Each panel module registers itself at
import time via :func:`register_panel`; :mod:`app.streaming.panels` imports
every submodule so registration actually happens.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.schemas.base import AppBaseModel

Translator = Callable[[str], Awaitable[str]]
Localizer = Callable[[dict, "Translator | None"], Awaitable[None]]


@dataclass(frozen=True)
class PanelSpec:
    kind: str
    model: type[AppBaseModel]
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
