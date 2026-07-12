"""``kind="air_quality"`` panel — the AQI drawer's model."""

from __future__ import annotations

from app.schemas.air_quality import AirQualityResponse
from app.schemas.base import AppBaseModel
from app.streaming.panels.base import PanelSpec, register_panel

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


register_panel(PanelSpec(kind="air_quality", model=AirQualityPanel))
