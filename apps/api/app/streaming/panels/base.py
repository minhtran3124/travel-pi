"""Panel registry: kind -> localizer lookup, and the set of valid kinds."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Localizer = Callable[[dict], Awaitable[None]]


class UnknownPanelKind(Exception):
    """Neither ``ValueError`` nor ``AppError``, so the panel tools' ``ToolException`` wrapping
    can't swallow a mistyped kind into a recoverable logic error instead of failing loudly."""


@dataclass(frozen=True)
class PanelSpec:
    kind: str
    localize_vi: Localizer | None = None


_REGISTRY: dict[str, PanelSpec] = {}


def register_panel(spec: PanelSpec) -> None:
    """Register a panel kind, raising on a duplicate ``kind``."""
    if spec.kind in _REGISTRY:
        raise ValueError(f"panel kind already registered: {spec.kind!r}")
    _REGISTRY[spec.kind] = spec


def get_panel(kind: str) -> PanelSpec | None:
    """Look up a registered panel spec by kind, or ``None`` if unregistered."""
    return _REGISTRY.get(kind)


def panel_kinds() -> tuple[str, ...]:
    """The registered panel kinds."""
    return tuple(_REGISTRY.keys())


def _swap(value: Any, table: dict[str, str]) -> Any:
    """Return ``table[value]`` when ``value`` is a mapped string, else ``value``."""
    if isinstance(value, str):
        return table.get(value, value)
    return value
