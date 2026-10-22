"""Unit tests for the curation-review guards in scripts/build_city_sources.py.

Covers the closure/former-status guard, the tip-evidence-relatedness guard and
the hotel price-floor/ceiling guard, using minimal fixture candidate/selection
files under a monkeypatched ``SPEC`` root. No network access.
"""

import json
from pathlib import Path

import pytest
from scripts import build_city_sources as bcs

_CITY = "Fixtureville"

_BASE_CANDIDATE = {
    "city": _CITY,
    "wikidata_qid": "Q1",
    "max_km": 15.0,
    "hotels": [],
    "places": [],
    "restaurants": [],
    "landmark_image": None,
    "wikipedia": {},
    "wikivoyage": {"Get around": "Take the number 4 tram to the old town square."},
}

_HOTEL_VALUES = {
    "amenities": ["Free WiFi"],
    "rating": 4.2,
    "review_count": 500,
    "property_type": "Hotel",
    "chain": None,
    "check_in_time": "15:00",
    "check_out_time": "11:00",
    "breakfast_included": False,
    "free_cancellation": True,
    "languages_spoken": ["English"],
}


def _candidate(**overrides) -> dict:
    cand = json.loads(json.dumps(_BASE_CANDIDATE))
    cand.update(overrides)
    return cand


def _hotel_candidate(qid: str, label: str, **overrides) -> dict:
    entry = {
        "qid": qid,
        "label": label,
        "latitude": 34.0,
        "longitude": 135.0,
        "image_url": None,
        "instance_of": [],
        "sitelinks": 1,
        "en_title": None,
        "strategy": "p131",
    }
    entry.update(overrides)
    return entry


def _hotel_selection(
    qid: str, star_rating: int, price_per_night: float, **overrides
) -> dict:
    sel = {
        "qid": qid,
        "star_rating": star_rating,
        "price_per_night": price_per_night,
        **_HOTEL_VALUES,
    }
    sel.update(overrides)
    return sel


@pytest.fixture(autouse=True)
def _fixture_city(tmp_path, monkeypatch):
    monkeypatch.setattr(bcs, "SPEC", tmp_path)
    monkeypatch.setattr(
        bcs,
        "CITIES",
        {
            **bcs.CITIES,
            _CITY: {
                "country": "Fixtureland",
                "airports": ["FXV"],
                "lat": 34.0,
                "lon": 135.0,
                "wiki": _CITY,
                "voyage": _CITY,
            },
        },
    )
    (tmp_path / "candidates").mkdir()
    (tmp_path / "selections").mkdir()
    return tmp_path


def _write(tmp_path: Path, candidate: dict, selection: dict) -> None:
    (tmp_path / "candidates" / f"{_CITY}.json").write_text(json.dumps(candidate))
    (tmp_path / "selections" / f"{_CITY}.json").write_text(json.dumps(selection))


# ---------------------------------------------------------------------------
# closure_match()
# ---------------------------------------------------------------------------


class TestClosureMatch:
    def test_flags_explicit_closure_keyword(self):
        assert bcs.closure_match("This grand hotel closed in 2019 after a fire.")

    def test_flags_past_tense_opening_sentence(self):
        assert bcs.closure_match(
            "The Beat Hotel was a small, run-down hotel of 42 rooms."
        )

    def test_no_match_for_operating_present_tense_text(self):
        assert (
            bcs.closure_match(
                "This is a five-star hotel in the city centre with a rooftop pool."
            )
            is None
        )

    def test_no_match_for_empty_extract(self):
        assert bcs.closure_match("") is None


# ---------------------------------------------------------------------------
# Closure guard wired into build_city() (hotels + places)
# ---------------------------------------------------------------------------


class TestClosureGuardInBuildCity:
    def test_hotel_with_closed_extract_and_no_status_reviewed_errors(self, tmp_path):
        cand = _candidate(
            hotels=[_hotel_candidate("Q100", "Old Grand Hotel")],
            wikipedia={
                "Q100": {
                    "title": "Old Grand Hotel",
                    "extract": "The hotel closed in 2020.",
                }
            },
        )
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q100", 4, 150)],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert any("closed/former" in e for e in errors)

    def test_hotel_with_closed_extract_and_status_reviewed_passes(self, tmp_path):
        cand = _candidate(
            hotels=[_hotel_candidate("Q100", "Old Grand Hotel")],
            wikipedia={
                "Q100": {
                    "title": "Old Grand Hotel",
                    "extract": "The hotel closed in 2020.",
                }
            },
        )
        sel = {
            "city": _CITY,
            "hotels": [
                _hotel_selection(
                    "Q100",
                    4,
                    150,
                    status_reviewed="renovated and reopened under new ownership in 2022",
                )
            ],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        result = bcs.build_city(_CITY, errors)

        assert not any("closed/former" in e for e in errors)
        assert result["hotels"][0]["name"] == "Old Grand Hotel"


# ---------------------------------------------------------------------------
# Tip-relatedness guard
# ---------------------------------------------------------------------------


class TestTipRelatednessGuard:
    def _base_sel(self, tip: dict) -> dict:
        return {"city": _CITY, "hotels": [], "places": [], "city_tips": [tip]}

    def test_unrelated_evidence_errors(self, tmp_path):
        cand = _candidate(
            wikivoyage={"Get around": "Take the number 4 tram to the old town square."}
        )
        tip = {
            "category": "food",
            "title": "Try the local dumplings",
            "content": "The night market sells cheap, delicious dumplings.",
            "is_essential": True,
            "evidence": "Take the number 4 tram to the old town square.",
        }
        _write(tmp_path, cand, self._base_sel(tip))

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert any("tip evidence unrelated" in e for e in errors)

    def test_related_evidence_passes(self, tmp_path):
        cand = _candidate(
            wikivoyage={
                "Eat": "The night market sells cheap, delicious dumplings every evening."
            }
        )
        tip = {
            "category": "food",
            "title": "Try the local dumplings",
            "content": "Visit the night market for cheap, delicious dumplings.",
            "is_essential": True,
            "evidence": "The night market sells cheap, delicious dumplings every evening.",
        }
        _write(tmp_path, cand, self._base_sel(tip))

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert not any("tip evidence unrelated" in e for e in errors)


# ---------------------------------------------------------------------------
# Price floor / budget ceiling guard
# ---------------------------------------------------------------------------


class TestPriceFloorGuard:
    def test_five_star_below_floor_errors(self, tmp_path):
        cand = _candidate(hotels=[_hotel_candidate("Q200", "Cheap Five Star")])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q200", 5, 120)],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert any("below the 5-star floor" in e for e in errors)

    def test_four_star_below_floor_errors(self, tmp_path):
        cand = _candidate(hotels=[_hotel_candidate("Q201", "Cheap Four Star")])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q201", 4, 60)],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert any("below the 4-star floor" in e for e in errors)

    def test_five_star_at_or_above_floor_passes(self, tmp_path):
        cand = _candidate(hotels=[_hotel_candidate("Q202", "Reasonable Five Star")])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q202", 5, 150)],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert not any("below the" in e and "floor" in e for e in errors)

    def test_hostel_above_ceiling_errors(self, tmp_path):
        cand = _candidate(hotels=[_hotel_candidate("Q203", "Overpriced Hostel")])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q203", 2, 250, property_type="Hostel")],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert any("too high" in e for e in errors)

    def test_budget_hostel_within_ceiling_passes(self, tmp_path):
        cand = _candidate(hotels=[_hotel_candidate("Q204", "Budget Hostel")])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q204", 2, 80, property_type="Hostel")],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert not any("too high" in e for e in errors)


# ---------------------------------------------------------------------------
# en_title name override
# ---------------------------------------------------------------------------


class TestEnTitleNameOverride:
    def test_hotel_uses_en_title_when_requested(self, tmp_path):
        cand = _candidate(
            hotels=[
                _hotel_candidate(
                    "Q300", "Historic Building Name", en_title="Modern Chain Hotel Name"
                )
            ]
        )
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q300", 5, 200, name="en_title")],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        result = bcs.build_city(_CITY, errors)

        assert result["hotels"][0]["name"] == "Modern Chain Hotel Name"

    def test_hotel_en_title_missing_errors(self, tmp_path):
        cand = _candidate(hotels=[_hotel_candidate("Q301", "Historic Building Name")])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection("Q301", 5, 200, name="en_title")],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        bcs.build_city(_CITY, errors)

        assert any(
            "selection asks for en_title name but the candidate has none" in e
            for e in errors
        )


# ---------------------------------------------------------------------------
# Same-QID-in-two-categories regression (hotel/restaurant collision)
# ---------------------------------------------------------------------------


class TestHotelPlaceCategoryCollision:
    def test_hotel_selection_resolves_even_when_same_qid_is_also_a_restaurant(
        self, tmp_path
    ):
        qid = "Q400"
        hotel_entry = _hotel_candidate(qid, "Ye Olde Pub Hotel")
        restaurant_entry = _hotel_candidate(
            qid, "Ye Olde Pub Hotel", instance_of=["pub"]
        )
        cand = _candidate(hotels=[hotel_entry], restaurants=[restaurant_entry])
        sel = {
            "city": _CITY,
            "hotels": [_hotel_selection(qid, 3, 100)],
            "places": [],
            "city_tips": [],
        }
        _write(tmp_path, cand, sel)

        errors: list[str] = []
        result = bcs.build_city(_CITY, errors)

        assert not any("is not a hotel candidate" in e for e in errors)
        assert result["hotels"][0]["wikidata"] == qid
