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
    "latitude": 34.6950,
    "longitude": 135.5010,
    "wikidata": "Q11681721",
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
    "wikidata": "Q210053",
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


def test_hotel_far_from_city_centre_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["hotels"][0]["latitude"] = 36.0  # far from Osaka's 34.65
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any(
        "hotel 'Hotel 0':" in v and "km from city centre" in v for v in violations
    ), violations


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
    assert any(
        "image_url does not start with https://upload.wikimedia.org/: "
        "'https://example.com/hotel.jpg'" in v
        for v in violations
    ), violations


def test_missing_source_url_is_flagged(tmp_path):
    entry = _good_city_entry()
    del entry["hotels"][0]["source_url"]
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("hotel 'Hotel 0': missing source_url" in v for v in violations), (
        violations
    )


def test_too_few_hotels_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["hotels"] = entry["hotels"][:3]
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("expected 6-8 hotels" in v for v in violations), violations


def test_missing_wikidata_on_hotel_is_flagged(tmp_path):
    entry = _good_city_entry()
    del entry["hotels"][0]["wikidata"]
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("wikidata is not a QID" in v for v in violations), violations


def test_malformed_wikidata_on_place_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["places"][0]["wikidata"] = "not-a-qid"
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("wikidata is not a QID" in v for v in violations), violations


def test_missing_hotel_latitude_is_flagged(tmp_path):
    entry = _good_city_entry()
    del entry["hotels"][0]["latitude"]
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("hotel 'Hotel 0': missing key 'latitude'" in v for v in violations), (
        violations
    )


def test_hotel_latitude_out_of_range_is_flagged(tmp_path):
    entry = _good_city_entry()
    entry["hotels"][0]["latitude"] = 95.0
    path = _write(tmp_path, "japan.json", [entry])
    violations = check_path(path)
    assert any("hotel 'Hotel 0': latitude out of range" in v for v in violations), (
        violations
    )


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


def test_foundations_airport_falls_back_to_country_centroid_when_city_unknown(
    tmp_path, capsys
):
    """No city file exists for 'Faraway City', so the airport is checked against
    its country's own centroid (2500 km, generous enough for a large country)
    instead, and a note is printed that the city radius was left unchecked."""
    foundations = {
        "countries": [
            {
                "name": "Bigland",
                "code": "BG",
                "region": "Nowhere",
                "latitude": 10.0,
                "longitude": 10.0,
                "source_url": "https://en.wikipedia.org/wiki/Bigland",
            }
        ],
        "visa": [],
        "airports": [
            {
                "code": "ZZZ",
                "name": "Faraway Field",
                "city": "Faraway City",
                "country": "Bigland",
                "latitude": 10.5,
                "longitude": 10.5,
                "source_url": "https://en.wikipedia.org/wiki/Faraway",
            }
        ],
        "airlines": [],
    }
    path = _write(tmp_path, "foundations.json", foundations)
    assert check_path(path) == []
    out = capsys.readouterr().out
    assert "city 'Faraway City' has no city file yet" in out
    assert "checked against Bigland's country centroid" in out


def test_foundations_airport_exceeds_country_centroid_radius_is_flagged(tmp_path):
    foundations = {
        "countries": [
            {
                "name": "Bigland",
                "code": "BG",
                "region": "Nowhere",
                "latitude": 10.0,
                "longitude": 10.0,
                "source_url": "https://en.wikipedia.org/wiki/Bigland",
            }
        ],
        "visa": [],
        "airports": [
            {
                "code": "ZZZ",
                "name": "Very Far Field",
                "city": "Very Far City",
                "country": "Bigland",
                "latitude": 60.0,
                "longitude": 60.0,
                "source_url": "https://en.wikipedia.org/wiki/VeryFar",
            }
        ],
        "airlines": [],
    }
    path = _write(tmp_path, "foundations.json", foundations)
    violations = check_path(path)
    assert any(
        "exceeds 2500.0 km" in v and "country-centroid fallback" in v
        for v in violations
    ), violations


def test_foundations_airport_note_when_neither_city_nor_country_known(tmp_path, capsys):
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
    out = capsys.readouterr().out
    assert "neither city 'Nowhere City' nor country 'Nowhere' centroid" in out


def test_duplicate_airport_code_across_run_is_flagged(tmp_path):
    foundations = {
        "countries": [],
        "visa": [],
        "airports": [
            {
                "code": "KIX",
                "name": "Kansai International Airport",
                "city": "Osaka",
                "country": "Japan",
                "latitude": 34.4347,
                "longitude": 135.244,
                "source_url": "https://en.wikipedia.org/wiki/Kansai_International_Airport",
            },
            {
                "code": "KIX",
                "name": "Duplicate Airport",
                "city": "Osaka",
                "country": "Japan",
                "latitude": 34.4347,
                "longitude": 135.244,
                "source_url": "https://en.wikipedia.org/wiki/Kansai_International_Airport",
            },
        ],
        "airlines": [],
    }
    path = _write(tmp_path, "foundations.json", foundations)
    violations = check_path(path)
    assert any("duplicate airport code 'KIX'" in v for v in violations), violations


def test_duplicate_airline_code_across_run_is_flagged(tmp_path):
    foundations = {
        "countries": [],
        "visa": [],
        "airports": [],
        "airlines": [
            {
                "code": "JL",
                "name": "Japan Airlines",
                "source_url": "https://en.wikipedia.org/wiki/Japan_Airlines",
            },
            {
                "code": "JL",
                "name": "Another Airline",
                "source_url": "https://en.wikipedia.org/wiki/Japan_Airlines",
            },
        ],
    }
    path = _write(tmp_path, "foundations.json", foundations)
    violations = check_path(path)
    assert any("duplicate airline code 'JL'" in v for v in violations), violations


def test_duplicate_country_name_and_code_across_run_is_flagged(tmp_path):
    foundations = {
        "countries": [
            {
                "name": "Japan",
                "code": "JP",
                "region": "East Asia",
                "latitude": 36.2048,
                "longitude": 138.2529,
                "source_url": "https://en.wikipedia.org/wiki/Japan",
            },
            {
                "name": "Japan",
                "code": "JP",
                "region": "East Asia",
                "latitude": 36.2048,
                "longitude": 138.2529,
                "source_url": "https://en.wikipedia.org/wiki/Japan",
            },
        ],
        "visa": [],
        "airports": [],
        "airlines": [],
    }
    path = _write(tmp_path, "foundations.json", foundations)
    violations = check_path(path)
    assert any("duplicate country name 'Japan'" in v for v in violations), violations
    assert any("duplicate country code 'JP'" in v for v in violations), violations


def test_duplicate_city_name_across_files_is_flagged(tmp_path):
    entry_a = _good_city_entry()
    entry_b = _good_city_entry()
    _write(tmp_path, "japan.json", [entry_a])
    _write(tmp_path, "japan_again.json", [entry_b])
    violations = check_path(tmp_path)
    assert any("duplicate city 'Osaka'" in v for v in violations), violations


def test_duplicate_hotel_city_name_pair_across_files_is_flagged(tmp_path):
    entry_a = _good_city_entry()
    entry_b = _good_city_entry()
    entry_b["city"]["name"] = "Kyoto"
    entry_b["hotels"][0]["name"] = "Hotel 0"  # collides with entry_a's hotel
    _write(tmp_path, "japan.json", [entry_a])
    _write(tmp_path, "japan_more.json", [entry_b])
    violations = check_path(tmp_path)
    # Different cities, same hotel name -> not itself a violation; the pair differs.
    assert not any("duplicate hotel (city, name)" in v for v in violations), violations

    entry_c = _good_city_entry()
    _write(tmp_path, "japan_dup.json", [entry_c])
    violations = check_path(tmp_path)
    assert any(
        "duplicate hotel (city, name) ('Osaka', 'Hotel 0')" in v for v in violations
    ), violations


def test_foundations_fx_block_passes_and_bad_date_is_flagged(tmp_path):
    from app.data.fx import LAST_UPDATED

    good_fx = {
        "date": LAST_UPDATED,
        "ecb": {
            "source_url": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
            "per_eur": {"USD": 1.1},
        },
        "pegs": [
            {
                "code": "AED",
                "rate": 3.6725,
                "basis": "fixed peg",
                "source_url": "https://www.centralbank.ae/",
            }
        ],
        "other": [
            {
                "code": "TWD",
                "rate": 31.78,
                "basis": "spot",
                "source_url": "https://rate.bot.com.tw/",
            }
        ],
    }
    foundations = {
        "countries": [],
        "visa": [],
        "airports": [],
        "airlines": [],
        "fx": good_fx,
    }
    path = _write(tmp_path, "foundations.json", foundations)
    assert check_path(path) == []

    bad_fx = dict(good_fx)
    bad_fx["date"] = "2000-01-01"
    foundations["fx"] = bad_fx
    path = _write(tmp_path, "foundations.json", foundations)
    violations = check_path(path)
    assert any(
        "fx: date '2000-01-01' does not match app.data.fx.LAST_UPDATED" in v
        for v in violations
    ), violations


def test_foundations_fx_peg_missing_source_url_is_flagged(tmp_path):
    from app.data.fx import LAST_UPDATED

    foundations = {
        "countries": [],
        "visa": [],
        "airports": [],
        "airlines": [],
        "fx": {
            "date": LAST_UPDATED,
            "ecb": {
                "source_url": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
                "per_eur": {"USD": 1.1},
            },
            "pegs": [{"code": "AED", "rate": 3.6725, "basis": "fixed peg"}],
            "other": [],
        },
    }
    path = _write(tmp_path, "foundations.json", foundations)
    violations = check_path(path)
    assert any("fx.pegs[0]" in v and "source_url" in v for v in violations), violations


def test_directory_scan_reports_ok(tmp_path, capsys):
    from scripts.check_seed_sources import main

    _write(tmp_path, "japan.json", [_good_city_entry()])
    exit_code = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK 1 files" in out
