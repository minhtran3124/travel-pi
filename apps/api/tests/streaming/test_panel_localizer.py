"""Unit tests for the deterministic side-panel localizer (Task 1.3).

Covers the ``en``/unknown identity no-op, ``vi`` deep-copy localization of the
bounded lookup tables, the injected-translator path for free-form place prose
(including its error fallback), and parity guards that keep each ``vi`` table
complete against its English source.
"""

import asyncio

from app.streaming.panel_localizer import localize_panel
from app.streaming.panels.air_quality import AQI_ADVICE_VI, AQI_CATEGORY_VI
from app.streaming.panels.hotels import AMENITY_VI
from app.streaming.panels.places import CATEGORY_VI
from app.streaming.panels.weather import WEATHER_VI


def test_en_is_identity():
    data = {"current": {"description": "Clear sky"}}
    assert asyncio.run(localize_panel("weather", data, "en")) is data


def test_unknown_language_is_identity():
    data = {"current": {"description": "Clear sky"}}
    assert asyncio.run(localize_panel("weather", data, "fr")) is data


def test_vi_localizes_weather_description():
    data = {"current": {"description": "Clear sky"}, "daily": []}
    out = asyncio.run(localize_panel("weather", data, "vi"))
    assert out["current"]["description"] == WEATHER_VI["Clear sky"]
    assert out is not data
    assert data["current"]["description"] == "Clear sky"


def test_vi_localizes_daily_weather_descriptions():
    data = {
        "current": {"description": "Clear sky"},
        "daily": [{"description": "Moderate rain"}, {"description": "Fog"}],
    }
    out = asyncio.run(localize_panel("weather", data, "vi"))
    assert out["daily"][0]["description"] == WEATHER_VI["Moderate rain"]
    assert out["daily"][1]["description"] == WEATHER_VI["Fog"]


def test_vi_unknown_bounded_value_passes_through():
    out = asyncio.run(
        localize_panel("weather", {"current": {"description": "??"}, "daily": []}, "vi")
    )
    assert out["current"]["description"] == "??"


def test_vi_places_description_uses_translator():
    calls = []

    async def translator(text):
        calls.append(text)
        return "TRANSLATED:" + text

    data = {"places": [{"description": "A cozy cafe.", "category": "cafe"}]}
    out = asyncio.run(localize_panel("places", data, "vi", translator=translator))
    assert out["places"][0]["description"] == "TRANSLATED:A cozy cafe."
    assert out["places"][0]["category"] == CATEGORY_VI["cafe"]
    assert calls == ["A cozy cafe."]


def test_vi_places_top_level_category_localized():
    data = {"category": "restaurant", "places": []}
    out = asyncio.run(localize_panel("places", data, "vi"))
    assert out["category"] == CATEGORY_VI["restaurant"]


def test_translator_error_falls_back_to_english():
    async def boom(text):
        raise RuntimeError("no llm")

    data = {"places": [{"description": "A cozy cafe.", "category": "cafe"}]}
    out = asyncio.run(localize_panel("places", data, "vi", translator=boom))
    assert out["places"][0]["description"] == "A cozy cafe."


def test_vi_air_quality_uses_forecast_key():
    data = {
        "category": "Good",
        "advice": "Air quality is satisfactory — enjoy the outdoors.",
        "forecast": [{"category": "Good"}],
    }
    out = asyncio.run(localize_panel("air_quality", data, "vi"))
    assert out["category"] == AQI_CATEGORY_VI["Good"]
    assert (
        out["advice"]
        == AQI_ADVICE_VI["Air quality is satisfactory — enjoy the outdoors."]
    )
    assert out["forecast"][0]["category"] == AQI_CATEGORY_VI["Good"]


def test_vi_hotels_amenities_localized():
    data = {"hotels": [{"amenities": ["Pool", "Spa", "Unknown Perk"]}]}
    out = asyncio.run(localize_panel("hotels", data, "vi"))
    assert out["hotels"][0]["amenities"][0] == AMENITY_VI["Pool"]
    assert out["hotels"][0]["amenities"][1] == AMENITY_VI["Spa"]
    # Unknown amenity passes through unchanged.
    assert out["hotels"][0]["amenities"][2] == "Unknown Perk"


def test_vi_tables_cover_english_sources():
    """Parity against the SOURCES, not against sibling derived tables.

    The AQI half used to compare ``AQI_CATEGORY_VI`` with ``_AQI_BAND`` — two tables
    both derived from the service, so the ``"Unknown"`` category (which the service
    emits when Open-Meteo has no reading, and which ``_AQI_BAND`` omits) fell through
    the gap and reached Vietnamese users in English. Enumerate what the service can
    actually return instead.
    """
    from app.services.air_quality_service import _us_aqi_category
    from app.services.weather_service import WMO_CODES
    from app.streaming.panels.air_quality import _AQI_ADVICE, _AQI_UNKNOWN_ADVICE

    wmo_values = set(WMO_CODES.values())
    assert wmo_values <= set(WEATHER_VI), wmo_values - set(WEATHER_VI)

    # Every category the service can produce, incl. the None -> "Unknown" fallback.
    service_categories = {_us_aqi_category(v) for v in [None, *range(0, 600, 5)]}
    assert service_categories <= set(AQI_CATEGORY_VI), service_categories - set(
        AQI_CATEGORY_VI
    )

    # Every advice sentence the panel can emit, incl. the unmapped-category fallback.
    panel_advice = set(_AQI_ADVICE.values()) | {_AQI_UNKNOWN_ADVICE}
    assert panel_advice <= set(AQI_ADVICE_VI), panel_advice - set(AQI_ADVICE_VI)


def test_vi_category_and_amenity_tables_cover_sources():
    from app.data.hotels import HOTELS
    from app.services.place_service import CATEGORY_META

    assert set(CATEGORY_META) <= set(CATEGORY_VI), set(CATEGORY_META) - set(CATEGORY_VI)
    seeded_amenities = {a for h in HOTELS for a in h.get("amenities", [])}
    assert seeded_amenities <= set(AMENITY_VI), seeded_amenities - set(AMENITY_VI)
