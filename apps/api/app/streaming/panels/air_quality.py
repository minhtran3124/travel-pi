"""``kind="air_quality"`` panel — the AQI drawer's model."""

from __future__ import annotations

from app.schemas.air_quality import AirQualityResponse
from app.schemas.base import AppBaseModel
from app.streaming.panels.base import PanelSpec, _swap, register_panel

# US-AQI category → presentation, mirroring the dashboard's aqi_* macros
# (templates/air_quality.html). Emoji + advice travel with the projection so the
# FE never re-owns the category mapping.
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

# US-AQI category → Vietnamese. Source of truth is every category
# ``air_quality_service._us_aqi_category`` can return, NOT ``_AQI_BAND`` above — that
# one is derived and omits the ``"Unknown"`` fallback the service emits with no reading.
AQI_CATEGORY_VI: dict[str, str] = {
    "Good": "Tốt",
    "Moderate": "Trung bình",
    "Unhealthy for Sensitive Groups": "Không tốt cho nhóm nhạy cảm",
    "Unhealthy": "Có hại cho sức khỏe",
    "Very Unhealthy": "Rất có hại cho sức khỏe",
    "Hazardous": "Nguy hiểm",
    "Unknown": "Không rõ",
}

# AQI advice sentence → Vietnamese. Covers every ``_AQI_ADVICE`` value plus
# ``_AQI_UNKNOWN_ADVICE``, which the panel emits whenever the category is unmapped.
AQI_ADVICE_VI: dict[str, str] = {
    "Air quality is satisfactory — enjoy the outdoors.": (
        "Chất lượng không khí tốt — thoải mái tận hưởng ngoài trời."
    ),
    "Acceptable, but unusually sensitive people should limit long exertion.": (
        "Ở mức chấp nhận được, nhưng người nhạy cảm nên hạn chế vận động lâu ngoài trời."
    ),
    "Sensitive groups should reduce prolonged outdoor exertion.": (
        "Nhóm nhạy cảm nên giảm vận động kéo dài ngoài trời."
    ),
    "Everyone may feel effects — limit time outdoors.": (
        "Mọi người đều có thể bị ảnh hưởng — hạn chế thời gian ở ngoài trời."
    ),
    "Health alert — avoid outdoor activity and mask up.": (
        "Cảnh báo sức khỏe — tránh hoạt động ngoài trời và đeo khẩu trang."
    ),
    "Emergency conditions — stay indoors with air filtered.": (
        "Tình trạng khẩn cấp — ở trong nhà với không khí đã được lọc."
    ),
    _AQI_UNKNOWN_ADVICE: (
        "Hiện chưa có số liệu chất lượng không khí cho địa điểm này."
    ),
}


async def _localize_vi(data: dict) -> None:
    """Swap ``category``/``advice``/``forecast[*].category`` to Vietnamese in place."""
    if isinstance(data.get("category"), str):
        data["category"] = _swap(data["category"], AQI_CATEGORY_VI)
    if isinstance(data.get("advice"), str):
        data["advice"] = _swap(data["advice"], AQI_ADVICE_VI)
    for day in data.get("forecast") or []:
        if isinstance(day, dict):
            day["category"] = _swap(day.get("category"), AQI_CATEGORY_VI)


class AirQualityPanelPollutant(AppBaseModel):
    label: str
    value: float | None = None
    unit: str
    desc: str


class AirQualityPanelDay(AppBaseModel):
    date: str
    max_us_aqi: int | None = None
    category: str
    emoji: str
    band: str


class AirQualityPanel(AppBaseModel):
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
        """Project a service ``AirQualityResponse`` into the AQI panel model."""
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


register_panel(PanelSpec(kind="air_quality", localize_vi=_localize_vi))
