"""``kind="hotels"`` panel — the hotels drawer's model."""

from __future__ import annotations

from app.schemas.base import AppBaseModel
from app.schemas.hotel import Hotel, HotelAvailability
from app.services.hotel_service import total_rooms
from app.streaming.panels.base import PanelSpec, _swap, register_panel

# Hotel amenity → Vietnamese. Must stay in parity with the distinct seeded amenities
# in ``app/data/hotels.py``.
AMENITY_VI: dict[str, str] = {
    "Air Conditioning": "Điều hòa",
    "Bar": "Quầy bar",
    "Beach Access": "Lối ra biển",
    "Free WiFi": "WiFi miễn phí",
    "Gym": "Phòng gym",
    "Hammocks": "Võng",
    "Pool": "Hồ bơi",
    "Restaurant": "Nhà hàng",
    "River View": "View sông",
    "Sea View": "View biển",
    "Shared Kitchen": "Bếp chung",
    "Spa": "Spa",
}


async def _localize_vi(data: dict) -> None:
    """Swap each hotel's ``amenities`` list to Vietnamese in place."""
    for hotel in data.get("hotels") or []:
        if isinstance(hotel, dict) and isinstance(hotel.get("amenities"), list):
            hotel["amenities"] = [_swap(a, AMENITY_VI) for a in hotel["amenities"]]


class HotelsPanelHotel(AppBaseModel):
    id: str
    image_url: str
    name: str
    star_rating: int
    price_per_night: float
    currency: str
    total_price: float
    available: bool
    available_rooms: int
    rating: float
    review_count: int
    amenities: list[str]
    description: str


class HotelsPanel(AppBaseModel):
    city: str
    check_in: str
    check_out: str
    nights: int
    rooms: int
    results_count: int
    cheapest_total: float
    hotels: list[HotelsPanelHotel]

    @classmethod
    def from_hotels(
        cls,
        city: str,
        check_in: str,
        check_out: str,
        nights: int,
        rooms: int,
        hotels: list[HotelAvailability],
    ) -> HotelsPanel:
        """Project the tool's hotel list into the panel model. The cheapest marker is the
        lowest all-in ``total_price`` (not nightly rate) — what the traveller actually pays."""
        return cls(
            city=city,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            rooms=rooms,
            results_count=len(hotels),
            cheapest_total=min(h.total_price for h in hotels),
            hotels=[
                HotelsPanelHotel(
                    id=h.id,
                    image_url=h.image_url,
                    name=h.name,
                    star_rating=h.star_rating,
                    price_per_night=h.price_per_night,
                    currency=h.currency,
                    total_price=h.total_price,
                    available=h.available,
                    available_rooms=h.available_rooms,
                    rating=h.rating,
                    review_count=h.review_count,
                    amenities=h.amenities,
                    description=h.description,
                )
                for h in hotels
            ],
        )

    @classmethod
    def from_catalog(cls, city: str, hotels: list[Hotel]) -> HotelsPanel:
        """Project a dateless catalog browse into the panel model. ``nights=0`` and empty
        dates let the FE tell a catalog browse from a dated search; every hotel is marked
        available and ``total_price`` falls back to the nightly rate."""
        return cls(
            city=city,
            check_in="",
            check_out="",
            nights=0,
            rooms=1,
            results_count=len(hotels),
            cheapest_total=min(h.price_per_night for h in hotels),
            hotels=[
                HotelsPanelHotel(
                    id=h.id,
                    image_url=h.image_url,
                    name=h.name,
                    star_rating=h.star_rating,
                    price_per_night=h.price_per_night,
                    currency=h.currency,
                    total_price=h.price_per_night,
                    available=True,
                    available_rooms=total_rooms(h),
                    rating=h.rating,
                    review_count=h.review_count,
                    amenities=h.amenities,
                    description=h.description,
                )
                for h in hotels
            ],
        )


register_panel(PanelSpec(kind="hotels", localize_vi=_localize_vi))
