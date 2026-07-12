"""``kind="hotels"`` panel — the hotels drawer's model."""

from __future__ import annotations

from app.schemas.base import AppBaseModel
from app.schemas.hotel import Hotel, HotelAvailability
from app.services.hotel_service import total_rooms
from app.streaming.panels.base import PanelSpec, register_panel


class HotelsPanelHotel(AppBaseModel):
    """One hotel row in a ``kind="hotels"`` panel."""

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


class HotelsPanel(AppBaseModel):
    """``data`` payload for a ``kind="hotels"`` panel — the hotels drawer's model."""

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
        """Project the tool's (non-empty) hotel list into the panel render model.

        Order is preserved (``check_availability`` returns them in seed order). The
        cheapest marker is the lowest all-in ``total_price`` (not nightly rate),
        which is what the traveller actually pays.

        :param city: Resolved city name echoed into the header.
        :param check_in: Check-in date echoed into the header.
        :param check_out: Check-out date echoed into the header.
        :param nights: Stay length in nights (from ``check_availability``).
        :param rooms: Rooms requested (echoed into the header).
        :param hotels: The non-empty availability list from ``HotelService``.
        :return: The hotels panel render model.
        """
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
                )
                for h in hotels
            ],
        )

    @classmethod
    def from_catalog(cls, city: str, hotels: list[Hotel]) -> HotelsPanel:
        """Project a dateless catalog browse (``browse_hotels``) into the panel render model.

        Unlike :meth:`from_hotels`, there are no dates or party size to echo — this
        is a catalog lookup, not an availability check. ``check_in``/``check_out``
        are left empty and ``nights`` is ``0`` so the FE can tell a catalog browse
        apart from a dated search; ``rooms`` defaults to ``1``. Each hotel is marked
        ``available=True`` with ``available_rooms`` set to its total room count
        (``total_rooms``) since no date range was checked, and ``total_price`` falls
        back to the nightly rate (no nights to multiply by).

        :param city: Resolved city name echoed into the header.
        :param hotels: The non-empty catalog list from ``HotelService.search_hotels``.
        :return: The hotels panel render model.
        """
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
                )
                for h in hotels
            ],
        )


register_panel(PanelSpec(kind="hotels", model=HotelsPanel))
