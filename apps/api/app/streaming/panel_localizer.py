"""Localize side-panel payloads to the traveller's language at emission time.

Side-panel ``data`` dicts (see ``app/streaming/panels.py``) carry English
strings baked in by the panel projections. When the conversation language is
``vi`` we swap the *bounded* strings (weather descriptions, AQI category +
advice, place categories, hotel amenities) via deterministic module-level lookup
tables — no LLM, so the mapping is stable and offline-safe. The only free-form
field, a place's ``description``, is translated through an *injected* translator
callable (never a direct ``get_fast_llm()`` call here) so ``FakeLLM`` tests stay
network-free.

``en`` (and any non-``vi`` language) is a strict identity no-op: the same object
is returned, unmodified and un-copied. ``vi`` deep-copies first so the persisted
checkpoint's English payload is never mutated in place.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

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

# US-AQI category → Vietnamese. One entry per KEY of ``_AQI_BAND`` in
# ``app/streaming/panels.py`` (parity-tested).
AQI_CATEGORY_VI: dict[str, str] = {
    "Good": "Tốt",
    "Moderate": "Trung bình",
    "Unhealthy for Sensitive Groups": "Không tốt cho nhóm nhạy cảm",
    "Unhealthy": "Có hại cho sức khỏe",
    "Very Unhealthy": "Rất có hại cho sức khỏe",
    "Hazardous": "Nguy hiểm",
}

# AQI advice sentence → Vietnamese. One entry per VALUE of ``_AQI_ADVICE`` in
# ``app/streaming/panels.py`` (parity-tested).
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
}

# Place category → Vietnamese. One entry per KEY of ``CATEGORY_META`` in
# ``app/services/place_service.py`` (parity-tested).
CATEGORY_VI: dict[str, str] = {
    "attraction": "điểm tham quan",
    "restaurant": "nhà hàng",
    "cafe": "quán cà phê",
    "activity": "hoạt động",
    "nightlife": "giải trí về đêm",
    "shopping": "mua sắm",
}

# Hotel amenity → Vietnamese. One entry per distinct seeded amenity in
# ``app/data/hotels.py`` (parity-tested).
AMENITY_VI: dict[str, str] = {
    "Air Conditioning": "Điều hòa",
    "Bar": "Quầy bar",
    "Beach Access": "Lối ra biển",
    "Free WiFi": "WiFi miễn phí",
    "Gym": "Phòng gym",
    "Hammocks": "Võng",
    "Pool": "Hồ bơi",
    "Restaurant": "Nhà hàng",
    "River View": "View sông",
    "Sea View": "View biển",
    "Shared Kitchen": "Bếp chung",
    "Spa": "Spa",
}

Translator = Callable[[str], Awaitable[str]]


def _swap(value: Any, table: dict[str, str]) -> Any:
    """Return ``table[value]`` when ``value`` is a mapped string, else ``value``.

    :param value: The candidate value (only ``str`` values are looked up).
    :param table: The English → Vietnamese lookup table.
    :return: The localized string, or the original value untouched.
    """
    if isinstance(value, str):
        return table.get(value, value)
    return value


async def localize_panel(
    kind: str,
    data: dict,
    language: str,
    translator: Translator | None = None,
) -> dict:
    """Localize a side-panel ``data`` dict to ``language``.

    ``en`` / any non-``vi`` language (and a non-dict ``data``) is an identity
    no-op — the SAME object is returned, unmodified. ``vi`` deep-copies ``data``
    then swaps the bounded strings via the module tables; for ``places`` a place's
    free-form ``description`` is translated through the injected ``translator``.

    :param kind: The panel kind (``weather`` / ``air_quality`` / ``places`` /
        ``hotels``); other kinds copy but localize nothing.
    :param data: The panel ``data`` projection to localize.
    :param language: The conversation language (only ``vi`` triggers work).
    :param translator: Callable used to translate free-form place prose; only
        consulted for ``kind == "places"`` under ``vi``. Never falls back to an
        LLM here — an absent translator leaves the English description in place.
    :return: The (possibly localized) panel data.
    """
    if language != "vi" or not isinstance(data, dict):
        return data

    out = copy.deepcopy(data)

    if kind == "weather":
        cur = out.get("current")
        if isinstance(cur, dict):
            cur["description"] = _swap(cur.get("description"), WEATHER_VI)
        for day in out.get("daily") or []:
            if isinstance(day, dict):
                day["description"] = _swap(day.get("description"), WEATHER_VI)

    elif kind == "air_quality":
        if isinstance(out.get("category"), str):
            out["category"] = _swap(out["category"], AQI_CATEGORY_VI)
        if isinstance(out.get("advice"), str):
            out["advice"] = _swap(out["advice"], AQI_ADVICE_VI)
        for day in out.get("forecast") or []:
            if isinstance(day, dict):
                day["category"] = _swap(day.get("category"), AQI_CATEGORY_VI)

    elif kind == "places":
        if isinstance(out.get("category"), str):
            out["category"] = _swap(out["category"], CATEGORY_VI)
        for place in out.get("places") or []:
            if not isinstance(place, dict):
                continue
            place["category"] = _swap(place.get("category"), CATEGORY_VI)
            desc = place.get("description")
            if translator and isinstance(desc, str) and desc:
                try:
                    place["description"] = await translator(desc)
                except Exception as e:  # noqa: BLE001
                    logger.error("[PANEL_LOCALIZER] translate failed: %s", e)

    elif kind == "hotels":
        for hotel in out.get("hotels") or []:
            if isinstance(hotel, dict) and isinstance(hotel.get("amenities"), list):
                hotel["amenities"] = [_swap(a, AMENITY_VI) for a in hotel["amenities"]]

    return out
