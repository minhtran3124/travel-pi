"""Unit tests for the import-time cross-reference guards in app/data/cities.py
and app/data/tips.py.

Each guard raises ValueError at module-import time when its referenced data is
missing or unrecognised. We prove that by patching the referenced source
(app.data.airports.AIRPORTS, app.data.cities.CITIES, app.enums.TipCategory) to
a "bad" value and reloading the guarded module, then restoring the source and
reloading again so later tests see the correct module state.
"""

import enum
import importlib

import app.data.airports as airports_module
import app.data.cities as cities_module
import app.data.tips as tips_module
import app.enums as enums_module
import pytest


def test_cities_rejects_unknown_airport_code():
    city_with_airport = next(c for c in cities_module.CITIES if c["airport_codes"])
    missing_code = city_with_airport["airport_codes"][0]

    original_airports = airports_module.AIRPORTS
    trimmed_airports = {
        code: value for code, value in original_airports.items() if code != missing_code
    }
    airports_module.AIRPORTS = trimmed_airports

    try:
        with pytest.raises(ValueError, match="unknown airport"):
            importlib.reload(cities_module)
    finally:
        airports_module.AIRPORTS = original_airports
        importlib.reload(cities_module)


def test_tips_rejects_unknown_city():
    known_tip_city = next(iter(tips_module.CITY_TIPS))

    original_cities = cities_module.CITIES
    trimmed_cities = [c for c in original_cities if c["name"] != known_tip_city]
    cities_module.CITIES = trimmed_cities

    try:
        with pytest.raises(ValueError, match="unknown cities"):
            importlib.reload(tips_module)
    finally:
        cities_module.CITIES = original_cities
        importlib.reload(tips_module)


def test_tips_rejects_unknown_category():
    original_category = enums_module.TipCategory
    fake_category = enum.Enum(
        "_FakeTipCategory",
        {
            name: member.value
            for name, member in original_category.__members__.items()
            if member.value != "transport"
        },
        type=str,
    )
    enums_module.TipCategory = fake_category

    try:
        with pytest.raises(ValueError, match="unknown tip category"):
            importlib.reload(tips_module)
    finally:
        enums_module.TipCategory = original_category
        importlib.reload(tips_module)
