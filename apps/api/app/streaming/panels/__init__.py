"""Side-panel artifact projections (specs/agent-side-panel).

A panel-capable tool returns ``(summary, artifact)`` via
``response_format="content_and_artifact"``; the artifact is
``{"kind": <kind>, "data": <projection>}``. The mapper forwards it as a
``panel`` SSE event and the FE renders by ``kind``. Projections are deliberately
lean — only what the drawer draws, not the full tool result (which would bloat
the persisted checkpoint).

Each panel kind lives in its own module and registers itself at import time
via ``register_panel``; ``panel_kinds()`` is the live list of registered
kinds (there is no separate ``Literal`` to keep in sync).

``RoutePanel``, ``WeatherPanel`` and ``AirQualityPanel`` exist today; the
``places`` projection landed alongside its ``search_places`` tool conversion.
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
