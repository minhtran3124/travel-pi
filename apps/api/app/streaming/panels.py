"""Side-panel artifact projections (specs/agent-side-panel).

A panel-capable tool returns ``(summary, artifact)`` via
``response_format="content_and_artifact"``; the artifact is
``{"kind": <PanelKind>, "data": <projection>}``. The mapper forwards it as a
``panel`` SSE event and the FE renders by ``kind``. Projections are deliberately
lean — only what the drawer draws, not the full tool result (which would bloat
the persisted checkpoint).

``RoutePanel``, ``WeatherPanel`` and ``AirQualityPanel`` exist today; the
``places`` projection lands alongside its tool conversion.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.air_quality import AirQualityResponse
from app.schemas.base import AppBaseModel
from app.schemas.route import RouteResponse
from app.schemas.weather import WeatherResponse
from app.services.weather_service import emoji_for_code

PanelKind = Literal["route", "places", "weather", "air_quality"]


def _gmaps_dir_url(o_lat: float, o_lng: float, d_lat: float, d_lng: float) -> str:
    """Keyless Google Maps directions deep-link (no API key required).

    :param o_lat: Origin latitude.
    :param o_lng: Origin longitude.
    :param d_lat: Destination latitude.
    :param d_lng: Destination longitude.
    :return: The Google Maps directions URL.
    """
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
        """Project a service ``RouteResponse`` into the route panel render model.

        :param r: The service route response to project.
        :return: The route panel render model.
        """
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
    """Bucket a WMO weather code into a sky mood the panel themes by.

    :param code: The WMO weather code.
    :return: The sky-mood bucket name.
    """
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
        """Project a service ``WeatherResponse`` into the weather panel render model.

        :param r: The service weather response to project.
        :return: The weather panel render model.
        """
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


# US-AQI category → presentation, mirroring the dashboard's aqi_* macros
# (templates/air_quality.html). Band keys the FE gradient/glow; emoji + advice
# travel with the projection so the panel never re-owns the category mapping.
_AQI_BAND = {
    "Good": "good",
    "Moderate": "moderate",
    "Unhealthy for Sensitive Groups": "usg",
    "Unhealthy": "unhealthy",
    "Very Unhealthy": "vunhealthy",
    "Hazardous": "hazardous",
}
_AQI_EMOJI = {
    "Good": "😊",
    "Moderate": "🙂",
    "Unhealthy for Sensitive Groups": "😷",
    "Unhealthy": "😨",
    "Very Unhealthy": "🤢",
    "Hazardous": "☠️",
}
_AQI_ADVICE = {
    "Good": "Air quality is satisfactory — enjoy the outdoors.",
    "Moderate": "Acceptable, but unusually sensitive people should limit long exertion.",
    "Unhealthy for Sensitive Groups": "Sensitive groups should reduce prolonged outdoor exertion.",
    "Unhealthy": "Everyone may feel effects — limit time outdoors.",
    "Very Unhealthy": "Health alert — avoid outdoor activity and mask up.",
    "Hazardous": "Emergency conditions — stay indoors with air filtered.",
}
_AQI_UNKNOWN_ADVICE = "No air-quality reading is available for this location right now."


class AirQualityPanelPollutant(AppBaseModel):
    """One pollutant readout of a ``kind="air_quality"`` panel."""

    label: str
    value: float | None = None
    unit: str
    desc: str


class AirQualityPanelDay(AppBaseModel):
    """One forecast card (peak AQI) of a ``kind="air_quality"`` panel."""

    date: str
    max_us_aqi: int | None = None
    category: str
    emoji: str
    band: str


class AirQualityPanel(AppBaseModel):
    """``data`` payload for a ``kind="air_quality"`` panel — the AQI drawer's model."""

    location_name: str
    country: str | None = None
    timezone: str
    time: str
    us_aqi: int | None = None
    category: str
    emoji: str
    band: str
    advice: str
    pollutants: list[AirQualityPanelPollutant]
    forecast: list[AirQualityPanelDay]
    attribution: str

    @classmethod
    def from_air_quality_response(cls, r: AirQualityResponse) -> AirQualityPanel:
        """Project a service ``AirQualityResponse`` into the AQI panel render model.

        :param r: The service air-quality response to project.
        :return: The AQI panel render model.
        """
        return cls(
            location_name=r.location.name,
            country=r.location.country,
            timezone=r.location.timezone,
            time=r.time,
            us_aqi=r.us_aqi,
            category=r.category,
            emoji=_AQI_EMOJI.get(r.category, "❓"),
            band=_AQI_BAND.get(r.category, "unknown"),
            advice=_AQI_ADVICE.get(r.category, _AQI_UNKNOWN_ADVICE),
            pollutants=[
                AirQualityPanelPollutant(
                    label="PM2.5", value=r.pm2_5, unit="μg/m³", desc="Fine particles"
                ),
                AirQualityPanelPollutant(
                    label="PM10", value=r.pm10, unit="μg/m³", desc="Coarse particles"
                ),
                AirQualityPanelPollutant(
                    label="Ozone", value=r.ozone, unit="μg/m³", desc="O₃"
                ),
                AirQualityPanelPollutant(
                    label="NO₂",
                    value=r.nitrogen_dioxide,
                    unit="μg/m³",
                    desc="Nitrogen dioxide",
                ),
                AirQualityPanelPollutant(
                    label="SO₂",
                    value=r.sulphur_dioxide,
                    unit="μg/m³",
                    desc="Sulphur dioxide",
                ),
                AirQualityPanelPollutant(
                    label="CO",
                    value=r.carbon_monoxide,
                    unit="μg/m³",
                    desc="Carbon monoxide",
                ),
            ],
            forecast=[
                AirQualityPanelDay(
                    date=d.date,
                    max_us_aqi=d.max_us_aqi,
                    category=d.category,
                    emoji=_AQI_EMOJI.get(d.category, "❓"),
                    band=_AQI_BAND.get(d.category, "unknown"),
                )
                for d in r.forecast
            ],
            attribution=r.attribution,
        )
