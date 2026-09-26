"""Unit tests for scripts/check_seed_sources.py against minimal fixture files."""

import json
from pathlib import Path

from scripts.check_seed_sources import check_path

_GOOD_HOTEL_TEMPLATE = {
    "address": "1-1 Osakajo, Chuo-ku",
    "star_rating": 4,
    "price_per_night": 120,
    "currency": "USD",
    "amenities": ["Restaurant", "Gym"],
    "image_url": "https://upload.wikimedia.org/wikipedia/commons/x/xx/Example.jpg",
    "rating": 4.5,
    "review_count": 2100,
    "description": "A pleasant hotel near the castle.",
    "property_type": "Hotel",
    "chain": None,
    "check_in_time": "15:00",
    "check_out_time": "11:00",
    "breakfast_included": False,
    "free_cancellation": True,
    "languages_spoken": ["English", "Japanese"],
    "source_url": "https://en.wikipedia.org/wiki/Osaka",
}

_GOOD_PLACE_TEMPLATE = {
    "category": "attraction",
    "description": "A famous castle.",
    "address": "1-1 Osakajo, Chuo-ku",
    "rating": 4.6,
    "review_count": 30000,
    "price_level": 1,
    "opening_hours": "09:00-17:00",
    "image_url": "https://upload.wikimedia.org/wikipedia/commons/x/xx/Castle.jpg",
    "tags": ["landmark", "history"],
    "is_recommended": True,
    "latitude": 34.6873,
    "longitude": 135.5262,
    "source_url": "https://en.wikipedia.org/wiki/Osaka_Castle",
}

_GOOD_TIP_TEMPLATE = {
    "category": "transport",
    "title": "Get an ICOCA card",
    "content": "Use a rechargeable IC card for trains and buses.",
    "is_essential": True,
    "source_url": "https://en.wikivoyage.org/wiki/Osaka",
}


def _make_hotel(name: str, **overrides) -> dict:
    hotel = {"name": name, **_GOOD_HOTEL_TEMPLATE}
    hotel.update(overrides)
    return hotel


def _make_place(name: str, lat: float, lon: float, **overrides) -> dict:
    place = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        **{
            k: v
            for k, v in _GOOD_PLACE_TEMPLATE.items()
            if k not in ("latitude", "longitude")
        },
    }
    place.update(overrides)
    return place


def _good_city_entry() -> dict:
    hotels = []
    for i in range(6):
        price = 100 if i < 3 else 200
        stars = 4 if i % 2 == 0 else 3
        hotels.append(
            _make_hotel(f"Hotel {i}", price_per_night=price, star_rating=stars)
        )

    places = []
    for i in range(6):
        places.append(_make_place(f"Attraction {i}", 34.6900 + i * 0.001, 135.5000))
    places.append(_make_place("Restaurant 1", 34.6900, 135.5000, category="restaurant"))
    places.append(_make_place("Cafe 1", 34.6900, 135.5000, category="cafe"))

    tips = [dict(_GOOD_TIP_TEMPLATE) for _ in range(3)]

    return {
        "city": {
            "name": "Osaka",
            "country": "Japan",
            "airport_codes": ["KIX"],
            "latitude": 34.6937,
            "longitude": 135.5023,
            "source_url": "https://en.wikipedia.org/wiki/Osaka",
        },
        "hotels": hotels,
        "places": places,
        "city_tips": tips,
    }


def _write(tmp_path, name: str, data) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_good_city_file_passes(tmp_path):
    path = _write(tmp_path, "japan.json", [_good_city_entry()])
    assert check_path(path) == []


def test_place_far_from_city_centre_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["places"][0]["latitude"] = 36.0  # far from Osaka's 34.65
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("km from city centre" in v for v in violations), violations


def test_invalid_coordinate_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["places"][0]["latitude"] = 95.0
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("latitude out of range" in v for v in violations), violations


def test_non_commons_image_url_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["hotels"][0]["image_url"] = "https://example.com/hotel.jpg"
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("upload.wikimedia.org" in v for v in violations), violations


def test_missing_source_url_is_flagged(tmp_path):
    entry = _good_city_entry()
    del entry["hotels"][0]["source_url"]
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("source_url" in v for v in violations), violations


def test_too_few_hotels_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["hotels"] = entry["hotels"][:3]
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("expected 6-8 hotels" in v for v in violations), violations


def test_countries_file_good_and_bad(tmp_path):
    good = [
        {
            "country": "France",
            "summary": "A large European country.",
            "summary_source_url": "https://en.wikivoyage.org/wiki/France",
            "tips": [dict(_GOOD_TIP_TEMPLATE) for _ in range(3)],
        }
    ]
    path = _write(tmp_path, "countries.json", good)
    assert check_path(path) == []

    bad = [
        {
            "country": "France",
            "summary": "A large European country.",
            "summary_source_url": "https://en.wikivoyage.org/wiki/France",
            "tips": [dict(_GOOD_TIP_TEMPLATE) for _ in range(2)],
        }
    ]
    path = _write(tmp_path, "countries_bad.json", bad)
    violations = check_path(path)
    assert any("expected >= 3 tips" in v for v in violations), violations


def test_foundations_airport_far_from_known_city_is_flagged(tmp_path):
    foundations = {
        "countries": [
            {
                "name": "Japan",
                "code": "JP",
                "region": "East Asia",
                "latitude": 36.2048,
                "longitude": 138.2529,
                "source_url": "https://en.wikipedia.org/wiki/Japan",
            }
        ],
        "visa": [],
        "airports": [
            {
                "code": "KIX",
                "name": "Kansai International Airport",
                "city": "Osaka",
                "country": "Japan",
                "latitude": 30.0,
                "longitude": 135.5023,
                "source_url": "https://en.wikipedia.org/wiki/Kansai_International_Airport",
            }
        ],
        "airlines": [],
    }
    _write(tmp_path, "foundations.json", foundations)
    _write(tmp_path, "japan.json", [_good_city_entry()])

    violations = check_path(tmp_path / "foundations.json")
    assert any("exceeds 80.0 km" in v for v in violations), violations


def test_foundations_airport_range_only_when_city_unknown(tmp_path):
    foundations = {
        "countries": [],
        "visa": [],
        "airports": [
            {
                "code": "ZZZ",
                "name": "Unknown Field Airport",
                "city": "Nowhere City",
                "country": "Nowhere",
                "latitude": 10.0,
                "longitude": 10.0,
                "source_url": "https://en.wikipedia.org/wiki/Nowhere",
            }
        ],
        "airlines": [],
    }
    path = _write(tmp_path, "foundations.json", foundations)
    assert check_path(path) == []


def test_directory_scan_reports_ok(tmp_path, capsys):
    from scripts.check_seed_sources import main

    _write(tmp_path, "japan.json", [_good_city_entry()])
    exit_code = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK 1 files" in out
