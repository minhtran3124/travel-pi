"""Drift test for scripts/import_seed_sources.py against app/data.

Renders the four seed modules' gh-237 blocks in memory straight from
specs/gh-237-city-coverage-expansion/sources/ (no network, no subprocess, no
disk write) and compares the parsed records to what is actually committed in
app.data.{cities,hotels,places,tips}. A hand edit inside a gh-237 block (or a
stale source file) makes the rendered records diverge from the committed ones
and fails this test -- byte-for-byte comparison of the rendered .py text isn't
used because it depends on a ruff-format pass to match the committed style.
"""

from ast import literal_eval

import pytest
from app.data.cities import CITIES
from app.data.hotels import HOTELS
from app.data.places import PLACES
from app.data.tips import CITY_TIPS, COUNTRY_SUMMARIES, COUNTRY_TIPS
from scripts.import_seed_sources import (
    load_city_files,
    load_countries,
    render_cities,
    render_city_tips,
    render_country_summaries,
    render_country_tips,
    render_hotels,
    render_places,
)


@pytest.fixture(scope="module")
def city_objs() -> list[dict]:
    return load_city_files()


@pytest.fixture(scope="module")
def countries() -> list[dict]:
    return load_countries()


def _parse_list(body: str) -> list[dict]:
    return literal_eval("[\n" + body + "]")


def _parse_dict(body: str) -> dict:
    return literal_eval("{\n" + body + "}")


def test_rendered_cities_match_app_data(city_objs):
    rendered = _parse_list(render_cities(city_objs))
    rendered_by_name = {c["name"]: c for c in rendered}
    actual_by_name = {c["name"]: c for c in CITIES if c["name"] in rendered_by_name}

    assert set(rendered_by_name) == set(actual_by_name)
    assert rendered_by_name == actual_by_name


def test_rendered_hotels_match_app_data(city_objs):
    rendered = _parse_list(render_hotels(city_objs))
    rendered_by_id = {h["id"]: h for h in rendered}
    # "country" is derived post-load (app/data/hotels.py backfills it from the
    # hotel's city), not part of the static, rendered record -- drop it before
    # comparing.
    actual_by_id = {
        h["id"]: {k: v for k, v in h.items() if k != "country"}
        for h in HOTELS
        if h["id"] in rendered_by_id
    }

    assert set(rendered_by_id) == set(actual_by_id)
    assert rendered_by_id == actual_by_id


def test_rendered_places_match_app_data(city_objs):
    rendered = _parse_list(render_places(city_objs))
    rendered_by_id = {p["id"]: p for p in rendered}
    actual_by_id = {p["id"]: p for p in PLACES if p["id"] in rendered_by_id}

    assert set(rendered_by_id) == set(actual_by_id)
    assert rendered_by_id == actual_by_id


def test_rendered_country_tips_match_app_data(countries):
    rendered = _parse_dict(render_country_tips(countries))
    actual = {k: v for k, v in COUNTRY_TIPS.items() if k in rendered}

    assert set(rendered) == set(actual)
    assert rendered == actual


def test_rendered_city_tips_match_app_data(city_objs):
    rendered = _parse_dict(render_city_tips(city_objs))
    actual = {k: v for k, v in CITY_TIPS.items() if k in rendered}

    assert set(rendered) == set(actual)
    assert rendered == actual


def test_rendered_country_summaries_match_app_data(countries):
    rendered_body = render_country_summaries(countries)
    rendered = literal_eval("{\n" + rendered_body + "}")
    actual = {k: v for k, v in COUNTRY_SUMMARIES.items() if k in rendered}

    assert set(rendered) == set(actual)
    assert rendered == actual
