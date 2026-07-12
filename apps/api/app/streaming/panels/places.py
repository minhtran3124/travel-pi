"""``kind="places"`` panel — the places drawer's model."""

from __future__ import annotations

import logging

from app.schemas.base import AppBaseModel
from app.schemas.place import Place
from app.streaming.panels.base import PanelSpec, Translator, _swap, register_panel

logger = logging.getLogger(__name__)

# Place category → Vietnamese. One entry per KEY of ``CATEGORY_META`` in
# ``app/services/place_service.py`` (parity-tested).
CATEGORY_VI: dict[str, str] = {
    "attraction": "điểm tham quan",
    "restaurant": "nhà hàng",
    "cafe": "quán cà phê",
    "activity": "hoạt động",
    "nightlife": "giải trí về đêm",
    "shopping": "mua sắm",
}


async def _localize_vi(data: dict, translator: Translator | None) -> None:
    """Swap ``category`` fields to Vietnamese and translate free-form ``description``.

    An absent ``translator`` leaves the English ``description`` in place; a
    translator failure is logged and also leaves the English text in place
    (never crashes the panel emission on a translation failure).

    :param data: The already-deep-copied ``places`` panel data dict.
    :param translator: Injected translator for free-form place prose; never
        falls back to an LLM call here.
    """
    if isinstance(data.get("category"), str):
        data["category"] = _swap(data["category"], CATEGORY_VI)
    for place in data.get("places") or []:
        if not isinstance(place, dict):
            continue
        place["category"] = _swap(place.get("category"), CATEGORY_VI)
        desc = place.get("description")
        if translator and isinstance(desc, str) and desc:
            try:
                place["description"] = await translator(desc)
            except Exception as e:  # noqa: BLE001
                logger.error("[PANEL_LOCALIZER] translate failed: %s", e)


class PlacesPanelPlace(AppBaseModel):
    """One place row in a ``kind="places"`` panel.

    Lean by design (mirrors ``HotelsPanelHotel``): only the fields the drawer
    draws. ``latitude``/``longitude`` are intentionally omitted — this panel has
    no map affordance.
    """

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
    """``data`` payload for a ``kind="places"`` panel — the places drawer's model."""

    city: str | None = None
    category: str | None = None
    results_count: int
    places: list[PlacesPanelPlace]

    @classmethod
    def from_places(
        cls, city: str | None, category: str | None, places: list[Place]
    ) -> PlacesPanel:
        """Project the tool's (non-empty) place list into the panel render model.

        Order is preserved (``search_places`` already applied the requested sort).
        ``city``/``category`` echo the query filters into the drawer header.

        :param city: City filter echoed into the header (may be None).
        :param category: Category filter echoed into the header (may be None).
        :param places: The non-empty place list from ``PlaceService.search_places``.
        :return: The places panel render model.
        """
        return cls(
            city=city,
            category=category,
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


register_panel(PanelSpec(kind="places", model=PlacesPanel, localize_vi=_localize_vi))
