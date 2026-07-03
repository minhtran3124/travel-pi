"""HotelService.resolve_amenities fuzzy-match (same bug class as MIN-50 category)."""


def test_resolve_amenities_matches_plural_and_substring(seeded_session):
    from app.services.hotel_service import HotelService

    svc = HotelService(seeded_session)
    assert svc.resolve_amenities(["wifi"]) == ["Free WiFi"]
    assert svc.resolve_amenities(["pool", "spa"]) == ["Pool", "Spa"]


def test_resolve_amenities_none_or_empty_is_no_op(seeded_session):
    from app.services.hotel_service import HotelService

    svc = HotelService(seeded_session)
    assert svc.resolve_amenities(None) is None
    assert svc.resolve_amenities([]) is None


def test_resolve_amenities_unmatched_passes_through(seeded_session):
    from app.services.hotel_service import HotelService

    svc = HotelService(seeded_session)
    assert svc.resolve_amenities(["breakfast"]) == ["breakfast"]


def test_search_hotels_amenity_typo_still_finds_matches(seeded_session):
    from app.services.hotel_service import HotelService

    svc = HotelService(seeded_session)
    baseline = svc.search_hotels("Da Nang", amenities=["Free WiFi"])
    fuzzy = svc.search_hotels("Da Nang", amenities=["wifi"])

    assert len(baseline) > 0
    assert [h.id for h in fuzzy] == [h.id for h in baseline]
