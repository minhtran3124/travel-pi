"""``kind="places"`` panel — the places drawer's model."""

from __future__ import annotations

from app.schemas.base import AppBaseModel
from app.schemas.place import Place
from app.streaming.panels.base import PanelSpec, register_panel


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


register_panel(PanelSpec(kind="places", model=PlacesPanel))
