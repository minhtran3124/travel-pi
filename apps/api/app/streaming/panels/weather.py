"""``kind="weather"`` panel — the forecast drawer's model."""

from __future__ import annotations

from app.schemas.base import AppBaseModel
from app.schemas.weather import WeatherResponse
from app.services.weather_service import emoji_for_code
from app.streaming.panels.base import PanelSpec, register_panel

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


register_panel(PanelSpec(kind="weather", model=WeatherPanel))
