"""Side-panel artifact projections (specs/agent-side-panel).

A panel-capable tool returns ``(summary, artifact)`` via
``response_format="content_and_artifact"``; the artifact is
``{"kind": <kind>, "data": <projection>}``. The mapper forwards it as a
``panel`` SSE event and the FE renders by ``kind``. Projections are deliberately
lean — only what the drawer draws, not the full tool result (which would bloat
the persisted checkpoint).

Each panel kind lives in its own module and registers itself at import time via
``register_panel``. The registry is the single declaration of a kind: ``panel_kinds()``
is the live list (no ``Literal`` to keep in sync), ``panel_result()`` in
``app/tools/_base.py`` rejects a kind that is not in it, and
``app/streaming/panel_localizer.py`` dispatches ``vi`` localization through it rather
than through a per-kind ``if`` chain.

To add a panel kind — create ONE file, ``panels/<kind>.py``:

1. Define the projection model (an ``AppBaseModel``) plus a ``from_*`` classmethod that
   projects the *service* response into it. Keep it lean: only what the drawer draws —
   the full tool result would bloat the persisted checkpoint.
2. If it carries bounded English strings (categories, descriptions, amenities), add the
   ``*_VI`` lookup table and an ``async def _localize_vi(data, translator) -> None`` that
   mutates ``data`` in place. Comment each table with the source of truth it must stay in
   parity with — the parity tests key off that. Free-form prose goes through the injected
   ``translator``; never call ``get_fast_llm()`` here.
3. Call ``register_panel(PanelSpec(kind=..., model=..., localize_vi=...))`` at module scope
   (omit ``localize_vi`` when the panel has no translatable strings — it then deep-copies
   and localizes nothing).
4. Import the module in this ``__init__`` (that import IS the registration) and add its
   public names to ``__all__``.

Nothing else needs editing — not the localizer, not a kind enum, not the mapper.

Original designs: ``specs/agent-side-panel`` (the panel mechanism) and
``specs/min-57-side-panel-language`` (localization).
"""

from __future__ import annotations

from app.streaming.panels.air_quality import (  # noqa: F401
    AirQualityPanel,
    AirQualityPanelDay,
    AirQualityPanelPollutant,
)
from app.streaming.panels.base import (  # noqa: F401
    PanelSpec,
    get_panel,
    panel_kinds,
    register_panel,
)
from app.streaming.panels.flights import FlightsPanel, FlightsPanelFlight  # noqa: F401
from app.streaming.panels.hotels import HotelsPanel, HotelsPanelHotel  # noqa: F401
from app.streaming.panels.places import PlacesPanel, PlacesPanelPlace  # noqa: F401
from app.streaming.panels.route import (  # noqa: F401
    RoutePanel,
    RoutePanelEndpoint,
    RoutePanelLeg,
)
from app.streaming.panels.weather import (  # noqa: F401
    WeatherPanel,
    WeatherPanelCurrent,
    WeatherPanelDay,
)

__all__ = [
    "AirQualityPanel",
    "AirQualityPanelDay",
    "AirQualityPanelPollutant",
    "FlightsPanel",
    "FlightsPanelFlight",
    "HotelsPanel",
    "HotelsPanelHotel",
    "PanelSpec",
    "PlacesPanel",
    "PlacesPanelPlace",
    "RoutePanel",
    "RoutePanelEndpoint",
    "RoutePanelLeg",
    "WeatherPanel",
    "WeatherPanelCurrent",
    "WeatherPanelDay",
    "get_panel",
    "panel_kinds",
    "register_panel",
]
