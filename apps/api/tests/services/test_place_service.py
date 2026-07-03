"""PlaceService.search_places exclude_names filter (MIN-50)."""


def test_search_places_exclude_names_omits_matches(seeded_session):
    from app.services.place_service import PlaceService

    svc = PlaceService(seeded_session)
    baseline = svc.search_places(city="Tokyo")
    assert len(baseline) == 4

    excluded = [baseline[0].name, baseline[1].name]
    filtered = svc.search_places(city="Tokyo", exclude_names=excluded)

    assert len(filtered) == len(baseline) - 2
    assert not set(excluded) & {p.name for p in filtered}


def test_search_places_exclude_names_none_is_no_op(seeded_session):
    from app.services.place_service import PlaceService

    svc = PlaceService(seeded_session)
    with_none = svc.search_places(city="Tokyo", exclude_names=None)
    without_arg = svc.search_places(city="Tokyo")
    assert [p.name for p in with_none] == [p.name for p in without_arg]
