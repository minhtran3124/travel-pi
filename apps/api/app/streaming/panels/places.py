"""``kind="places"`` panel — the places drawer's model."""

from __future__ import annotations

from app.schemas.base import AppBaseModel
from app.schemas.place import Place
from app.streaming.panels.base import PanelSpec, _swap, register_panel

# Place category → Vietnamese. Must stay in parity with the keys of ``CATEGORY_META``
# in ``app/services/place_service.py``.
CATEGORY_VI: dict[str, str] = {
    "attraction": "điểm tham quan",
    "restaurant": "nhà hàng",
    "cafe": "quán cà phê",
    "activity": "hoạt động",
    "nightlife": "giải trí về đêm",
    "shopping": "mua sắm",
}


async def _localize_vi(data: dict) -> None:
    """Swap ``category`` fields to Vietnamese. Free-form ``description`` is left alone —
    ``search_places`` already localized it from the ``content_translations`` store."""
    if isinstance(data.get("category"), str):
        data["category"] = _swap(data["category"], CATEGORY_VI)
    for place in data.get("places") or []:
        if isinstance(place, dict):
            place["category"] = _swap(place.get("category"), CATEGORY_VI)


class PlacesPanelPlace(AppBaseModel):
    """``latitude``/``longitude`` are omitted — this panel has no map affordance."""

    id: str
    name: str
    city: str
    country: str
    category: str
    description: str
    address: str
    rating: float
    review_count: int
    price_level: int
    opening_hours: str | None = None
    image_url: str
    tags: list[str]
    is_recommended: bool


class PlacesPanel(AppBaseModel):
    city: str | None = None
    category: str | None = None
    # Canonical slug for the frontend's panel identity, never localized — unlike
    # ``category`` above, which ``_localize_vi`` rewrites and would otherwise split
    # one category into two drawer tabs mid-conversation.
    category_key: str | None = None
    results_count: int
    places: list[PlacesPanelPlace]

    @classmethod
    def from_places(
        cls, city: str | None, category: str | None, places: list[Place]
    ) -> PlacesPanel:
        """Project the tool's place list into the panel model, preserving its sort order."""
        return cls(
            city=city,
            category=category,
            category_key=category,
            results_count=len(places),
            places=[
                PlacesPanelPlace(
                    id=p.id,
                    name=p.name,
                    city=p.city,
                    country=p.country,
                    category=p.category,
                    description=p.description,
                    address=p.address,
                    rating=p.rating,
                    review_count=p.review_count,
                    price_level=p.price_level,
                    opening_hours=p.opening_hours,
                    image_url=p.image_url,
                    tags=p.tags,
                    is_recommended=p.is_recommended,
                )
                for p in places
            ],
        )


register_panel(PanelSpec(kind="places", localize_vi=_localize_vi))
