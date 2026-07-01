"""HotelsPanel projection (specs/hotels-side-panel Task 1.1)."""

from app.schemas.hotel import Hotel, HotelAvailability
from app.streaming.panels import HotelsPanel


def _hotel(hid: str, name: str, stars: int, price: float) -> Hotel:
    return Hotel(
        id=hid,
        code="DAD001",
        name=name,
        city="Da Nang",
        country="Vietnam",
        address="1 Beach Rd",
        star_rating=stars,
        price_per_night=price,
        currency="USD",
        amenities=["wifi", "pool"],
        image_url="https://example.com/img.jpg",
        rating=4.5,
        review_count=120,
        description="A nice hotel.",
        property_type="Hotel",
        chain="Independent",
        check_in_time="14:00",
        check_out_time="12:00",
        breakfast_included=True,
        free_cancellation=True,
        languages_spoken=["English"],
    )


def _avail(hotel: Hotel, available: bool, free: int, total: float) -> HotelAvailability:
    return HotelAvailability(
        **hotel.model_dump(),
        available=available,
        available_rooms=free,
        max_occupancy_per_room=3,
        nights=4,
        total_price=total,
    )


def test_from_hotels_projects_all_fields_and_cheapest():
    hotels = [_hotel("h1", "Grand", 4, 120.0), _hotel("h2", "Seaside", 5, 80.0)]
    avails = [
        _avail(hotels[0], True, 10, 480.0),
        _avail(hotels[1], True, 5, 320.0),
    ]
    panel = HotelsPanel.from_hotels("Da Nang", "2027-04-10", "2027-04-14", 4, 1, avails)

    assert panel.city == "Da Nang"
    assert panel.check_in == "2027-04-10"
    assert panel.check_out == "2027-04-14"
    assert panel.nights == 4 and panel.rooms == 1
    assert panel.results_count == 2
    assert panel.cheapest_total == 320.0
    assert [h.name for h in panel.hotels] == ["Grand", "Seaside"]  # order preserved
    row = panel.hotels[0]
    assert row.star_rating == 4
    assert row.price_per_night == 120.0 and row.currency == "USD"
    assert row.total_price == 480.0
    assert row.available is True and row.available_rooms == 10
    assert row.rating == 4.5 and row.review_count == 120
    assert row.amenities == ["wifi", "pool"]
    assert row.short_code.startswith("HTL-")
