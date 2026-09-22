"""Phu Quoc seed inventory: enough budget/mid hotels and restaurants/cafes, all localized."""

import json
from pathlib import Path

from app.data.hotels import HOTELS
from app.data.places import PLACES

_VI_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "data"
    / "content_translations.vi.json"
)


def _pq_hotels() -> list[dict]:
    return [h for h in HOTELS if h["city"] == "Phu Quoc"]


def _pq_places(category: str) -> list[dict]:
    return [p for p in PLACES if p["city"] == "Phu Quoc" and p["category"] == category]


def _vi_ids() -> set[str]:
    rows = json.loads(_VI_PATH.read_text(encoding="utf-8"))
    return {r["entity_id"] for r in rows if r["field"] == "description"}


def test_phu_quoc_has_budget_hotels():
    budget = [h for h in _pq_hotels() if h["price_per_night"] < 60]
    assert len(budget) >= 3, [(h["code"], h["price_per_night"]) for h in _pq_hotels()]


def test_phu_quoc_has_mid_range_hotels():
    mid = [h for h in _pq_hotels() if 60 <= h["price_per_night"] <= 130]
    assert len(mid) >= 2, [(h["code"], h["price_per_night"]) for h in _pq_hotels()]


def test_phu_quoc_has_restaurants_and_cafes():
    assert len(_pq_places("restaurant")) >= 4
    assert len(_pq_places("cafe")) >= 3


def test_phu_quoc_hotel_codes_are_unique_and_sequential():
    codes = [h["code"] for h in _pq_hotels()]
    assert len(codes) == len(set(codes))
    assert {"PQC004", "PQC005", "PQC006", "PQC007", "PQC008"} <= set(codes)


def test_new_phu_quoc_rows_have_vietnamese_translations():
    vi_ids = _vi_ids()
    new_hotel_ids = [
        h["id"]
        for h in _pq_hotels()
        if h["code"] in {"PQC004", "PQC005", "PQC006", "PQC007", "PQC008"}
    ]
    new_place_ids = [
        p["id"]
        for p in PLACES
        if p["city"] == "Phu Quoc" and p["category"] in {"restaurant", "cafe"}
    ]
    missing = [i for i in new_hotel_ids + new_place_ids if i not in vi_ids]
    assert not missing, missing


def test_seed_ids_are_unique_across_catalog():
    hotel_ids = [h["id"] for h in HOTELS]
    place_ids = [p["id"] for p in PLACES]
    assert len(hotel_ids) == len(set(hotel_ids))
    assert len(place_ids) == len(set(place_ids))
