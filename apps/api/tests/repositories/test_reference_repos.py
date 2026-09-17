"""Parity tests: each reference repo reproduces today's ``app/data`` structures over a seeded temp DB."""

import pytest
from app.data.airlines import AIRLINE_COLORS, AIRLINES
from app.data.airports import AIRPORTS
from app.data.cities import CITIES
from app.data.countries import COUNTRIES
from app.data.fx import COUNTRY_CURRENCY, CURRENCY_NAMES, LAST_UPDATED, RATES
from app.data.hotels import HOTELS
from app.data.places import PLACES
from app.data.tips import CITY_TIPS, COUNTRY_SUMMARIES, COUNTRY_TIPS
from app.data.visa import COUNTRY_VISA
from app.db import models
from app.db.base import Base, deterministic_uuid
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.repositories.airline import AirlineRepository
from app.repositories.airport import AirportRepository
from app.repositories.city import CityRepository
from app.repositories.country import CountryRepository
from app.repositories.fx import FxRepository
from app.repositories.hotel_ref import HotelRepository
from app.repositories.place_ref import PlaceRepository
from app.repositories.tip import TipRepository
from app.repositories.visa import VisaRepository
from app.schemas.airport import Airport
from app.schemas.city import City
from app.schemas.hotel import Hotel
from app.schemas.place import Place
from app.schemas.tip import Tip
from app.schemas.visa import EntryRequirements
from sqlalchemy import func, select


@pytest.fixture(scope="module")
def sf(tmp_path_factory):
    """A seeded temp-SQLite session factory shared by the module's tests."""
    db_file = tmp_path_factory.mktemp("refrepos") / "ref.db"
    url = f"sqlite:///{db_file}"
    Base.metadata.create_all(get_engine(url))
    seed_all(get_session_factory(url))
    return get_session_factory(url)


def test_airline_list_preserves_seed_order(sf):
    """list() must return airlines in AIRLINES seed order (position) as {code, name} dicts, since flight_service does rng.choice over a seeded RNG."""
    repo = AirlineRepository(sf)
    result = repo.list()
    expected = [{"code": a["code"], "name": a["name"]} for a in AIRLINES]
    assert result == expected


def test_airline_color(sf):
    repo = AirlineRepository(sf)
    for code, color in AIRLINE_COLORS.items():
        assert repo.color(code) == color
    assert repo.color("ZZ") is None


def test_airport_list_and_get(sf):
    repo = AirportRepository(sf)
    listed = repo.list()
    assert all(isinstance(a, Airport) for a in listed)
    assert len(listed) == len(AIRPORTS)
    by_code = {a.code: a for a in listed}
    for code, info in AIRPORTS.items():
        a = by_code[code]
        assert a.code == code  # ORM PK is `iata`, schema field is `code`
        assert a.name == info["name"]
        assert a.city == info["city"]
        assert a.country == info["country"]


def test_airport_get_is_case_insensitive(sf):
    repo = AirportRepository(sf)
    any_code = next(iter(AIRPORTS))
    got = repo.get(any_code.lower())
    assert got is not None
    assert got.code == any_code
    assert repo.get("zzz") is None


def test_country_list_and_get(sf):
    repo = CountryRepository(sf)
    listed = repo.list()
    assert len(listed) == len(COUNTRIES)
    # Seed order (ORDER BY position) is preserved — the dashboard region tiles rely on it.
    assert [c["code"] for c in listed] == [c["code"] for c in COUNTRIES]
    by_code = {c["code"]: c for c in listed}
    for c in COUNTRIES:
        got = by_code[c["code"]]
        assert got["name"] == c["name"]
        assert got["region"] == c["region"]
    one = COUNTRIES[0]
    assert repo.get(one["code"])["name"] == one["name"]
    assert repo.get("ZZ") is None


def test_country_distinct_names(sf):
    repo = CountryRepository(sf)
    expected = sorted({c["country"] for c in CITIES})
    assert repo.distinct_names() == expected


def test_visa_get(sf):
    repo = VisaRepository(sf)
    for country, v in COUNTRY_VISA.items():
        got = repo.get(country)
        assert isinstance(got, EntryRequirements)
        assert got.visa_free_days == v["visa_free_days"]
        assert got.visa_on_arrival == v["visa_on_arrival"]
        assert got.e_visa == v["e_visa"]
        assert got.passport_validity_months == v["passport_validity_months"]
        assert got.summary == v["summary"]
    assert repo.get("Atlantis") is None


def test_fx_rate_and_name(sf):
    repo = FxRepository(sf)
    for code, rate in RATES.items():
        assert repo.rate(code) == rate
        assert repo.name(code) == CURRENCY_NAMES.get(code, code)
    assert repo.rate("ZZZ") is None
    assert repo.name("ZZZ") is None


def test_fx_country_currency_and_last_updated(sf):
    repo = FxRepository(sf)
    for country, code in COUNTRY_CURRENCY.items():
        assert repo.country_currency(country) == code
    assert repo.country_currency("Atlantis") is None
    assert repo.last_updated() == LAST_UPDATED


def test_fx_valid_codes_and_country_names(sf):
    repo = FxRepository(sf)
    assert repo.valid_codes() == sorted(RATES)
    assert repo.country_names() == sorted(COUNTRY_CURRENCY)


def _hotel_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for h in HOTELS:
        counts[h["city"]] = counts.get(h["city"], 0) + 1
    return counts


def test_city_distinct_names(sf):
    repo = CityRepository(sf)
    assert sorted(repo.distinct_names()) == sorted(c["name"] for c in CITIES)


def test_city_get(sf):
    repo = CityRepository(sf)
    counts = _hotel_counts()
    sample = CITIES[0]
    got = repo.get(sample["name"])
    assert isinstance(got, City)
    assert got.name == sample["name"]
    assert got.country == sample["country"]
    assert got.airport_codes == sample["airport_codes"]
    assert got.hotel_count == counts.get(sample["name"], 0)
    assert repo.get(sample["name"].lower()).name == sample["name"]
    assert repo.get("Nowhere City") is None


def test_city_list_with_counts(sf):
    repo = CityRepository(sf)
    counts = _hotel_counts()
    listed = repo.list_with_counts()
    assert all(isinstance(c, City) for c in listed)
    assert len(listed) == len(CITIES)
    by_name = {c.name: c for c in listed}
    for c in CITIES:
        assert by_name[c["name"]].hotel_count == counts.get(c["name"], 0)


def test_hotel_count_by_city(sf):
    repo = HotelRepository(sf)
    assert repo.count_by_city() == _hotel_counts()


def test_hotel_all_and_get(sf):
    repo = HotelRepository(sf)
    all_hotels = repo.all()
    assert all(isinstance(h, Hotel) for h in all_hotels)
    assert len(all_hotels) == len(HOTELS)
    sample = HOTELS[0]
    got = repo.get(sample["id"])
    assert got is not None
    assert got.id == sample["id"]  # verbatim → MD5 availability stays identical
    assert got.country == sample["country"]
    assert repo.get("does-not-exist") is None


def test_hotel_by_short_code(sf):
    repo = HotelRepository(sf)
    sample = repo.all()[0]
    got = repo.by_short_code(sample.short_code)
    assert got is not None and got.id == sample.id
    assert repo.by_short_code(sample.short_code.lower()).id == sample.id
    assert repo.by_short_code("HTL-NOPE99") is None


def test_hotel_search_city_filter(sf):
    repo = HotelRepository(sf)
    city = HOTELS[0]["city"]
    results = repo.search(city=city)
    expected = [h["id"] for h in HOTELS if h["city"] == city]
    assert sorted(h.id for h in results) == sorted(expected)


def test_hotel_search_stars_and_price(sf):
    repo = HotelRepository(sf)
    city = HOTELS[0]["city"]
    results = repo.search(city=city, min_stars=4, max_price=200.0)
    for h in results:
        assert h.star_rating >= 4
        assert h.price_per_night <= 200.0


def test_hotel_search_amenities_all_contains(sf):
    repo = HotelRepository(sf)
    # Find a city + amenity that actually exists so the assertion is meaningful.
    city = HOTELS[0]["city"]
    in_city = [h for h in HOTELS if h["city"] == city]
    amenity = in_city[0]["amenities"][0]
    results = repo.search(city=city, amenities=[amenity.upper()])  # case-insensitive
    expected = [
        h["id"]
        for h in in_city
        if amenity.lower() in [a.lower() for a in h["amenities"]]
    ]
    assert sorted(h.id for h in results) == sorted(expected)
    assert len(results) > 0


def test_hotel_distinct_cities(sf):
    repo = HotelRepository(sf)
    assert repo.distinct_cities() == sorted({h["city"] for h in HOTELS})


def test_place_all_and_get(sf):
    repo = PlaceRepository(sf)
    all_places = repo.all()
    assert all(isinstance(p, Place) for p in all_places)
    assert len(all_places) == len(PLACES)
    sample = PLACES[0]
    got = repo.get(sample["id"])
    assert got is not None and got.id == sample["id"]
    assert repo.get("nope") is None


def test_place_by_short_code(sf):
    repo = PlaceRepository(sf)
    sample = repo.all()[0]
    got = repo.by_short_code(sample.short_code)
    assert got is not None and got.id == sample.id
    assert repo.by_short_code(sample.short_code.lower()).id == sample.id
    assert repo.by_short_code("PLC-NOPE99") is None


def test_place_distinct_cities_and_categories(sf):
    repo = PlaceRepository(sf)
    assert repo.distinct_cities() == sorted({p["city"] for p in PLACES})
    assert repo.distinct_categories() == sorted({p["category"] for p in PLACES})


def test_place_search_filters(sf):
    repo = PlaceRepository(sf)
    city = PLACES[0]["city"]
    category = PLACES[0]["category"]
    results = repo.search(city=city, category=category)
    expected = [
        p["id"]
        for p in PLACES
        if p["city"] == city and p["category"].lower() == category.lower()
    ]
    assert sorted(p.id for p in results) == sorted(expected)


def test_place_search_rating_and_price(sf):
    repo = PlaceRepository(sf)
    results = repo.search(min_rating=4.5, price_level_max=2)
    for p in results:
        assert p.rating >= 4.5
        assert p.price_level <= 2
    exact = repo.search(price_level=1)
    assert all(p.price_level == 1 for p in exact)


def test_place_search_recommended(sf):
    repo = PlaceRepository(sf)
    results = repo.search(recommended=True)
    assert all(p.is_recommended for p in results)
    expected = [p["id"] for p in PLACES if p.get("is_recommended", False)]
    assert sorted(p.id for p in results) == sorted(expected)


def test_tip_for_location_country_ordering_and_ids(sf):
    repo = TipRepository(sf)
    country = next(iter(COUNTRY_TIPS))
    tips = repo.for_location("country", country)
    assert all(isinstance(t, Tip) for t in tips)
    raw = COUNTRY_TIPS[country]
    assert len(tips) == len(raw)
    # ordered by position, ids are deterministic UUID5 over (scope, key, pos)
    for i, (t, r) in enumerate(zip(tips, raw, strict=True)):
        assert t.id == deterministic_uuid("tip", "country", country, str(i))
        assert t.scope == "country"
        assert t.title == r["title"]
        assert t.content == r["content"]
        assert t.is_essential == r.get("is_essential", False)


def test_tip_known_id_stable(sf):
    repo = TipRepository(sf)
    tips = repo.for_location("country", "Vietnam")
    assert tips[0].id == deterministic_uuid("tip", "country", "Vietnam", "0")


def test_tip_for_location_city(sf):
    repo = TipRepository(sf)
    city = next(iter(CITY_TIPS))
    tips = repo.for_location("city", city)
    assert len(tips) == len(CITY_TIPS[city])
    assert all(t.scope == "city" for t in tips)


def test_tip_all_tips_merges_country_and_city(sf):
    repo = TipRepository(sf)
    all_tips = repo.all_tips()
    total = sum(len(v) for v in COUNTRY_TIPS.values()) + sum(
        len(v) for v in CITY_TIPS.values()
    )
    assert len(all_tips) == total


def test_tip_country_summary(sf):
    repo = TipRepository(sf)
    for country, summary in COUNTRY_SUMMARIES.items():
        assert repo.country_summary(country) == summary
    assert repo.country_summary("Atlantis") == ""


def test_repos_are_read_only_count_unchanged(sf):
    """Sanity: exercising the repos doesn't mutate the seeded tables."""
    with sf() as s:
        before = s.scalar(select(func.count()).select_from(models.Tip))
    TipRepository(sf).all_tips()
    PlaceRepository(sf).all()
    with sf() as s:
        after = s.scalar(select(func.count()).select_from(models.Tip))
    assert before == after
