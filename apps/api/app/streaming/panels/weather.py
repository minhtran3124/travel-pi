"""``kind="weather"`` panel — the forecast drawer's model."""

from __future__ import annotations

from app.schemas.base import AppBaseModel
from app.schemas.weather import WeatherResponse
from app.services.weather_service import emoji_for_code
from app.streaming.panels.base import PanelSpec, Translator, _swap, register_panel

# WMO code → sky-mood bucket, mirroring the dashboard's ``cond_class`` macro
# (templates/weather.html). Drives the hero gradient + card tint on the FE.
_COND_CLOUD = frozenset({3, 45, 48})
_COND_SNOW = frozenset({71, 73, 75, 77, 85, 86})
_COND_STORM = frozenset({95, 96, 99})

# WMO weather description → Vietnamese. One entry per value in
# ``app/services/weather_service.py`` WMO_CODES (parity-tested).
WEATHER_VI: dict[str, str] = {
    "Clear sky": "Trời quang",
    "Mainly clear": "Trời khá quang",
    "Partly cloudy": "Có mây rải rác",
    "Overcast": "Trời nhiều mây",
    "Fog": "Sương mù",
    "Depositing rime fog": "Sương muối",
    "Light drizzle": "Mưa phùn nhẹ",
    "Moderate drizzle": "Mưa phùn",
    "Dense drizzle": "Mưa phùn dày hạt",
    "Light freezing drizzle": "Mưa phùn băng giá nhẹ",
    "Dense freezing drizzle": "Mưa phùn băng giá dày hạt",
    "Slight rain": "Mưa nhỏ",
    "Moderate rain": "Mưa vừa",
    "Heavy rain": "Mưa to",
    "Light freezing rain": "Mưa băng giá nhẹ",
    "Heavy freezing rain": "Mưa băng giá nặng hạt",
    "Slight snow fall": "Tuyết rơi nhẹ",
    "Moderate snow fall": "Tuyết rơi vừa",
    "Heavy snow fall": "Tuyết rơi dày",
    "Snow grains": "Hạt tuyết",
    "Slight rain showers": "Mưa rào nhẹ",
    "Moderate rain showers": "Mưa rào",
    "Violent rain showers": "Mưa rào dữ dội",
    "Slight snow showers": "Mưa tuyết nhẹ",
    "Heavy snow showers": "Mưa tuyết nặng hạt",
    "Thunderstorm": "Giông bão",
    "Thunderstorm with slight hail": "Giông kèm mưa đá nhẹ",
    "Thunderstorm with heavy hail": "Giông kèm mưa đá lớn",
}


async def _localize_vi(data: dict, translator: Translator | None) -> None:
    """Swap ``current``/``daily`` weather descriptions to Vietnamese in place.

    :param data: The already-deep-copied ``weather`` panel data dict.
    :param translator: Unused — ``weather`` has no free-form prose.
    """
    cur = data.get("current")
    if isinstance(cur, dict):
        cur["description"] = _swap(cur.get("description"), WEATHER_VI)
    for day in data.get("daily") or []:
        if isinstance(day, dict):
            day["description"] = _swap(day.get("description"), WEATHER_VI)


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


register_panel(PanelSpec(kind="weather", model=WeatherPanel, localize_vi=_localize_vi))
