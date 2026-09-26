"""Unit tests for country-alias resolution (app/data/countries.py)."""

from app.data.countries import COUNTRIES, COUNTRY_ALIASES, resolve_country_alias

_CANONICAL_NAMES = {c["name"] for c in COUNTRIES}


def test_resolve_country_alias_us_variants():
    for alias in ("US", "USA", "U.S.", "U.S.A.", "America", "United States of America"):
        assert resolve_country_alias(alias) == "United States"


def test_resolve_country_alias_uk_variants():
    for alias in (
        "UK",
        "U.K.",
        "Britain",
        "Great Britain",
        "England",
        "Scotland",
        "Wales",
    ):
        assert resolve_country_alias(alias) == "United Kingdom"


def test_resolve_country_alias_uae_variants():
    for alias in ("UAE", "U.A.E.", "Emirates"):
        assert resolve_country_alias(alias) == "United Arab Emirates"


def test_resolve_country_alias_turkey_variants():
    assert resolve_country_alias("Türkiye") == "Turkey"
    assert resolve_country_alias("Turkiye") == "Turkey"


def test_resolve_country_alias_south_korea_variants():
    assert resolve_country_alias("Korea") == "South Korea"
    assert resolve_country_alias("Republic of Korea") == "South Korea"


def test_resolve_country_alias_is_case_and_whitespace_insensitive():
    assert resolve_country_alias("  usa  ") == "United States"
    assert resolve_country_alias("uk") == "United Kingdom"


def test_resolve_country_alias_unknown_name_returns_none():
    assert resolve_country_alias("France") is None
    assert resolve_country_alias("Austria") is None


def test_resolve_country_alias_targets_are_seeded_countries():
    # Every alias target must itself be a real seeded country so a resolver never
    # forwards a name the rest of the lookup pipeline can't recognise.
    assert set(COUNTRY_ALIASES.values()) <= _CANONICAL_NAMES
