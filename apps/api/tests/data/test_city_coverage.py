"""Coverage checks for the 20 new cities added by gh-237 (city-coverage-expansion).

Parametrized over NEW_CITIES; asserts the Global Constraints coverage rules from
specs/gh-237-city-coverage-expansion/PLAN.md: airport codes registered, 6-8 hotels
(>=2 at or under $130, >=2 of 4-star+), 8+ places (>=5 attractions, >=2 restaurant
or cafe), 3+ CITY_TIPS, the country present in visa/fx/tips/summaries, and a vi
translation row for every new hotel/place id. These fail until the later waves of
the plan add the actual city/hotel/place/tip/translation data (waves 3-4).
"""

import json
import re
from pathlib import Path

import pytest
from app.data.airports import AIRPORTS
from app.data.cities import CITIES
from app.data.fx import COUNTRY_CURRENCY, RATES
from app.data.hotels import HOTELS
from app.data.places import PLACES
from app.data.tips import CITY_TIPS, COUNTRY_SUMMARIES, COUNTRY_TIPS
from app.data.visa import COUNTRY_VISA

NEW_CITIES = [
    "Osaka",
    "Kyoto",
    "Fukuoka",
    "Sapporo",
    "Busan",
    "Jeju",
    "Taipei",
    "Shanghai",
    "Beijing",
    "Guangzhou",
    "Paris",
    "London",
    "Lisbon",
    "Rome",
    "Sydney",
    "Melbourne",
    "Dubai",
    "Istanbul",
    "New York",
    "Los Angeles",
]

_VI_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "data"
    / "content_translations.vi.json"
)


def _vi_ids() -> set[str]:
    rows = json.loads(_VI_PATH.read_text(encoding="utf-8"))
    return {r["entity_id"] for r in rows if r["field"] == "description"}


def _city_record(name: str) -> dict | None:
    return next((c for c in CITIES if c["name"] == name), None)


def _hotels_for(city: str) -> list[dict]:
    return [h for h in HOTELS if h["city"] == city]


def _places_for(city: str) -> list[dict]:
    return [p for p in PLACES if p["city"] == city]


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_has_airport_codes_registered(city):
    record = _city_record(city)
    assert record is not None, f"{city}: missing from app.data.cities.CITIES"
    assert record["airport_codes"], f"{city}: has no airport_codes"
    missing = [code for code in record["airport_codes"] if code not in AIRPORTS]
    assert not missing, f"{city}: airport codes not registered in AIRPORTS: {missing}"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_hotel_counts(city):
    hotels = _hotels_for(city)
    assert 6 <= len(hotels) <= 8, (
        f"{city}: expected 6-8 hotels in app.data.hotels, got {len(hotels)}"
    )
    cheap = [h for h in hotels if h["price_per_night"] <= 130]
    assert len(cheap) >= 2, (
        f"{city}: expected >=2 hotels priced <=130, got {len(cheap)}"
    )
    good = [h for h in hotels if h["star_rating"] >= 4]
    assert len(good) >= 2, f"{city}: expected >=2 hotels of 4-star+, got {len(good)}"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_place_counts(city):
    places = _places_for(city)
    assert len(places) >= 8, (
        f"{city}: expected >=8 places in app.data.places, got {len(places)}"
    )
    attractions = [p for p in places if p["category"] == "attraction"]
    assert len(attractions) >= 5, (
        f"{city}: expected >=5 attraction places, got {len(attractions)}"
    )
    food = [p for p in places if p["category"] in ("restaurant", "cafe")]
    assert len(food) >= 2, (
        f"{city}: expected >=2 restaurant/cafe places, got {len(food)}"
    )


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_has_city_tips(city):
    tips = CITY_TIPS.get(city, [])
    assert len(tips) >= 3, f"{city}: expected >=3 CITY_TIPS, got {len(tips)}"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_country_reference_data_present(city):
    record = _city_record(city)
    assert record is not None, f"{city}: missing from app.data.cities.CITIES"
    country = record["country"]
    assert country in COUNTRY_VISA, f"{country}: missing from COUNTRY_VISA"
    assert country in COUNTRY_CURRENCY, f"{country}: missing from COUNTRY_CURRENCY"
    currency = COUNTRY_CURRENCY.get(country)
    assert currency in RATES, f"{country}: currency {currency!r} missing from RATES"
    assert country in COUNTRY_TIPS, f"{country}: missing from COUNTRY_TIPS"
    assert country in COUNTRY_SUMMARIES, f"{country}: missing from COUNTRY_SUMMARIES"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_hotels_and_places_have_vi_translations(city):
    vi_ids = _vi_ids()
    missing = [h["id"] for h in _hotels_for(city) if h["id"] not in vi_ids]
    missing += [p["id"] for p in _places_for(city) if p["id"] not in vi_ids]
    assert not missing, (
        f"{city}: missing vi description translations for ids: {missing}"
    )


@pytest.mark.parametrize("city", NEW_CITIES)
def test_city_hotel_codes_are_unique_and_match_city_prefix(city):
    """Hotel ``code`` = the city's primary IATA code + a 3-digit sequence (Global
    Constraints): Kyoto uses its IATA metropolitan city code ``UKY`` (it has no
    airport of its own; see PRIMARY_AIRPORT in test_new_city_search.py), every
    other city uses its real (first) airport code, e.g. Osaka -> KIX."""
    hotels = _hotels_for(city)
    codes = [h.get("code") for h in hotels]
    assert len(codes) == len(set(codes)), f"{city}: duplicate hotel codes: {codes}"

    if city == "Kyoto":
        prefix = "UKY"
    else:
        record = _city_record(city)
        assert record is not None, f"{city}: missing from app.data.cities.CITIES"
        assert record["airport_codes"], f"{city}: has no airport_codes"
        prefix = record["airport_codes"][0]

    pattern = re.compile(rf"^{re.escape(prefix)}\d{{3}}$")
    bad = [c for c in codes if not isinstance(c, str) or not pattern.match(c)]
    assert not bad, f"{city}: hotel codes not matching ^{prefix}\\d{{3}}$: {bad}"
