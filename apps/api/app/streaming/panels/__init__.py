"""Side-panel artifact projections, one module per kind, each self-registering at import."""

from __future__ import annotations

from app.streaming.panels.air_quality import (  # noqa: F401
    AirQualityPanel,
    AirQualityPanelDay,
    AirQualityPanelPollutant,
)
from app.streaming.panels.base import (  # noqa: F401
    PanelSpec,
    UnknownPanelKind,
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
    "UnknownPanelKind",
    "WeatherPanel",
    "WeatherPanelCurrent",
    "WeatherPanelDay",
    "get_panel",
    "panel_kinds",
    "register_panel",
]
