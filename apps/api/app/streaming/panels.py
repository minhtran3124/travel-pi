"""Side-panel artifact projections (specs/agent-side-panel).

A panel-capable tool returns ``(summary, artifact)`` via
``response_format="content_and_artifact"``; the artifact is
``{"kind": <PanelKind>, "data": <projection>}``. The mapper forwards it as a
``panel`` SSE event and the FE renders by ``kind``. Projections are deliberately
lean — only what the drawer draws, not the full tool result (which would bloat
the persisted checkpoint).

``RoutePanel`` and ``WeatherPanel`` exist today; the ``places`` projection lands
alongside its tool conversion.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import AppBaseModel
from app.schemas.route import RouteResponse
from app.schemas.weather import WeatherResponse
from app.services.weather_service import emoji_for_code

PanelKind = Literal["route", "places", "weather"]


def _gmaps_dir_url(o_lat: float, o_lng: float, d_lat: float, d_lng: float) -> str:
    """Keyless Google Maps directions deep-link (no API key required)."""
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={o_lat},{o_lng}&destination={d_lat},{d_lng}"
    )


class RoutePanelEndpoint(AppBaseModel):
    name: str
    lat: float
    lng: float


class RoutePanelLeg(AppBaseModel):
    mode: str
    distance_km: float
    duration_minutes: float


class RoutePanel(AppBaseModel):
    """``data`` payload for a ``kind="route"`` panel — the map drawer's model."""

    origin: RoutePanelEndpoint
    destination: RoutePanelEndpoint
    recommended_mode: str
    legs: list[RoutePanelLeg]
    straight_line_km: float
    source: str
    geometry: list[list[float]] | None = None
    gmaps_url: str

    @classmethod
    def from_route_response(cls, r: RouteResponse) -> RoutePanel:
        """Project a service ``RouteResponse`` into the route panel render model."""
        return cls(
            origin=RoutePanelEndpoint(
                name=r.origin.name, lat=r.origin.latitude, lng=r.origin.longitude
            ),
            destination=RoutePanelEndpoint(
                name=r.destination.name,
                lat=r.destination.latitude,
                lng=r.destination.longitude,
            ),
            recommended_mode=r.recommended_mode,
            legs=[
                RoutePanelLeg(
                    mode=leg.mode,
                    distance_km=leg.distance_km,
                    duration_minutes=leg.duration_minutes,
                )
                for leg in r.legs
            ],
            straight_line_km=r.straight_line_km,
            source=r.source,
            geometry=r.geometry,
            gmaps_url=_gmaps_dir_url(
                r.origin.latitude,
                r.origin.longitude,
                r.destination.latitude,
                r.destination.longitude,
            ),
        )


# WMO code → sky-mood bucket, mirroring the dashboard's ``cond_class`` macro
# (templates/weather.html). Drives the hero gradient + card tint on the FE.
_COND_CLOUD = frozenset({3, 45, 48})
_COND_SNOW = frozenset({71, 73, 75, 77, 85, 86})
_COND_STORM = frozenset({95, 96, 99})


def _condition(code: int) -> str:
    """Bucket a WMO weather code into a sky mood the panel themes by."""
    if code in (0, 1):
        return "clear"
    if code == 2:
        return "partly"
    if code in _COND_CLOUD:
        return "cloud"
    if code in _COND_SNOW:
        return "snow"
    if code in _COND_STORM:
        return "storm"
    return "rain"


class WeatherPanelCurrent(AppBaseModel):
    """Current conditions block of a ``kind="weather"`` panel."""

    temperature_c: float
    apparent_temperature_c: float
    relative_humidity: int
    wind_speed_kmh: float
    description: str
    emoji: str
    condition: str
    time: str


class WeatherPanelDay(AppBaseModel):
    """One forecast card of a ``kind="weather"`` panel."""

    date: str
    temp_min_c: float
    temp_max_c: float
    precipitation_probability_max: int | None = None
    description: str
    emoji: str
    condition: str


class WeatherPanel(AppBaseModel):
    """``data`` payload for a ``kind="weather"`` panel — the forecast drawer's model."""

    location_name: str
    country: str | None = None
    timezone: str
    current: WeatherPanelCurrent
    daily: list[WeatherPanelDay]
    attribution: str

    @classmethod
    def from_weather_response(cls, r: WeatherResponse) -> WeatherPanel:
        """Project a service ``WeatherResponse`` into the weather panel render model."""
        return cls(
            location_name=r.location.name,
            country=r.location.country,
            timezone=r.location.timezone,
            current=WeatherPanelCurrent(
                temperature_c=r.current.temperature_c,
                apparent_temperature_c=r.current.apparent_temperature_c,
                relative_humidity=r.current.relative_humidity,
                wind_speed_kmh=r.current.wind_speed_kmh,
                description=r.current.description,
                emoji=emoji_for_code(r.current.weather_code),
                condition=_condition(r.current.weather_code),
                time=r.current.time,
            ),
            daily=[
                WeatherPanelDay(
                    date=d.date,
                    temp_min_c=d.temp_min_c,
                    temp_max_c=d.temp_max_c,
                    precipitation_probability_max=d.precipitation_probability_max,
                    description=d.description,
                    emoji=emoji_for_code(d.weather_code),
                    condition=_condition(d.weather_code),
                )
                for d in r.daily
            ],
            attribution=r.attribution,
        )
