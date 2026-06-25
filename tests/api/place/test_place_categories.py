"""Tests for GET /places/categories — name + color + icon metadata."""

import re

from app.services.place_service import _FALLBACK, CATEGORY_META
from fastapi.testclient import TestClient

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_categories_item_shape(client: TestClient) -> None:
    cats = client.get("/places/categories").json()
    assert cats, "expected at least one category"
    for c in cats:
        assert set(c) == {"name", "color", "icon"}
        assert isinstance(c["name"], str) and c["name"]
        assert _HEX.match(c["color"]), c["color"]
        assert isinstance(c["icon"], str) and c["icon"]


def test_categories_color_icon_match_metadata(client: TestClient) -> None:
    """Each returned category carries the color/icon from CATEGORY_META."""
    for c in client.get("/places/categories").json():
        color, icon = CATEGORY_META.get(c["name"], _FALLBACK)
        assert c["color"] == color
        assert c["icon"] == icon


def test_every_seed_category_has_metadata(client: TestClient) -> None:
    """No seed-derived category may fall through to the neutral fallback —
    a newly-seeded category without a CATEGORY_META entry fails loudly here."""
    names = [c["name"] for c in client.get("/places/categories").json()]
    missing = [n for n in names if n not in CATEGORY_META]
    assert not missing, f"categories without metadata: {missing}"


def test_unknown_category_falls_back() -> None:
    """An unmapped category resolves to the neutral fallback, never an error."""
    assert CATEGORY_META.get("does-not-exist", _FALLBACK) == _FALLBACK
    assert _HEX.match(_FALLBACK[0])
