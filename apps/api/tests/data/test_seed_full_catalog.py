"""Full-catalog seed check: seed_all() completes cleanly against a fresh temp
SQLite DB (including the short_code collision check), and each new city's
hotel/place row counts match app.data.hotels / app.data.places. Fails until the
later waves of specs/gh-237-city-coverage-expansion/PLAN.md add the actual city
data (waves 3-4); the row-count assertions are the expected red signal until then.
"""

import pytest
from app.data.hotels import HOTELS
from app.data.places import PLACES
from app.db import models
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from sqlalchemy import select

from tests.data.test_city_coverage import NEW_CITIES


@pytest.fixture()
def seeded_session_factory(tmp_path):
    db_url = f"sqlite:///{tmp_path}/t.db"
    Base.metadata.create_all(get_engine(db_url), checkfirst=True)
    seed_all(get_session_factory(db_url))  # raises on short_code collision
    return get_session_factory(db_url)


def test_seed_all_completes_without_short_code_collision(seeded_session_factory):
    with seeded_session_factory() as session:
        assert session.scalar(select(models.Hotel).limit(1)) is not None
        assert session.scalar(select(models.Place).limit(1)) is not None


@pytest.mark.parametrize("city", NEW_CITIES)
def test_new_city_hotel_row_count_matches_data_module(seeded_session_factory, city):
    expected = len([h for h in HOTELS if h["city"] == city])
    assert expected >= 6, (
        f"{city}: app.data.hotels has no seeded hotel rows yet (found {expected})"
    )
    with seeded_session_factory() as session:
        actual = len(
            session.scalars(select(models.Hotel).where(models.Hotel.city == city)).all()
        )
    assert actual == expected, (
        f"{city}: DB hotel row count {actual} != app.data.hotels count {expected}"
    )


@pytest.mark.parametrize("city", NEW_CITIES)
def test_new_city_place_row_count_matches_data_module(seeded_session_factory, city):
    expected = len([p for p in PLACES if p["city"] == city])
    assert expected >= 8, (
        f"{city}: app.data.places has no seeded place rows yet (found {expected})"
    )
    with seeded_session_factory() as session:
        actual = len(
            session.scalars(select(models.Place).where(models.Place.city == city)).all()
        )
    assert actual == expected, (
        f"{city}: DB place row count {actual} != app.data.places count {expected}"
    )
