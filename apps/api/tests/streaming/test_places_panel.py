"""PlacesPanel projection (specs/places-side-panel Task 1.1)."""

import asyncio

from app.schemas.place import Place
from app.streaming.panel_localizer import localize_panel
from app.streaming.panels import PlacesPanel


def _place(pid: str, name: str, rating: float, recommended: bool = False) -> Place:
    return Place(
        id=pid,
        name=name,
        city="Tokyo",
        country="Japan",
        category="attraction",
        description="A nice place.",
        address="1 Main St",
        rating=rating,
        review_count=200,
        price_level=2,
        opening_hours="Mon-Sun 09:00-22:00",
        image_url="https://example.com/img.jpg",
        tags=["family-friendly", "outdoor"],
        is_recommended=recommended,
        latitude=35.68,
        longitude=139.76,
    )


def test_from_places_projects_all_fields_and_preserves_order():
    places = [
        _place("p1", "Senso-ji", 4.8, recommended=True),
        _place("p2", "Shibuya Crossing", 4.5),
    ]
    panel = PlacesPanel.from_places("Tokyo", "attraction", places)

    assert panel.city == "Tokyo"
    assert panel.category == "attraction"
    assert panel.category_key == "attraction"
    assert panel.results_count == 2
    assert [p.name for p in panel.places] == ["Senso-ji", "Shibuya Crossing"]  # order

    row = panel.places[0]
    assert row.id == "p1"
    assert row.name == "Senso-ji"
    assert row.city == "Tokyo" and row.country == "Japan"
    assert row.category == "attraction"
    assert row.description == "A nice place."
    assert row.address == "1 Main St"
    assert row.rating == 4.8 and row.review_count == 200
    assert row.price_level == 2
    assert row.opening_hours == "Mon-Sun 09:00-22:00"
    assert row.image_url == "https://example.com/img.jpg"
    assert row.tags == ["family-friendly", "outdoor"]
    assert row.is_recommended is True


def test_from_places_omits_coordinates():
    panel = PlacesPanel.from_places("Tokyo", None, [_place("p1", "Senso-ji", 4.8)])

    dumped = panel.places[0].model_dump()
    assert "latitude" not in dumped
    assert "longitude" not in dumped


def test_from_places_allows_none_filters():
    panel = PlacesPanel.from_places(None, None, [_place("p1", "Senso-ji", 4.8)])

    assert panel.city is None
    assert panel.category is None
    assert panel.category_key is None
    assert panel.results_count == 1


def test_localize_vi_leaves_category_key_raw():
    # `category_key` is the frontend's panel-identity slug — it must survive a
    # language switch untouched even as the display `category` is localized.
    panel = PlacesPanel.from_places(
        "Tokyo", "attraction", [_place("p1", "Senso-ji", 4.8)]
    )
    out = asyncio.run(localize_panel("places", panel.model_dump(), "vi"))

    assert out["category"] != "attraction"
    assert out["category_key"] == "attraction"
