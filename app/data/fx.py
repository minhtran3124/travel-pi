"""Static, USD-based mock foreign-exchange table.

This is **mock data** — no live rates, no network call. ``LAST_UPDATED`` is a
fixed date so the response is honest about being a snapshot. ``RATES`` is keyed
by ISO 4217 code and gives *units of that currency per 1 USD* (so USD == 1.0);
a cross-rate is ``RATES[to] / RATES[from]``.

Covers every seed-country currency (see ``data/countries.py``) plus a few common
reference currencies. ``COUNTRY_CURRENCY`` maps each country name to its code so
``/currency/convert`` can surface a destination's local currency. The mapping is
validated against ``COUNTRIES`` at import — a missing or mistyped entry fails
loudly on startup, like the other seed files.
"""

from app.data.countries import COUNTRIES

LAST_UPDATED = "2026-06-01"

# units of currency per 1 USD (USD is the base, == 1.0)
RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "AUD": 1.51,
    "VND": 25400.0,
    "THB": 36.5,
    "SGD": 1.35,
    "MYR": 4.72,
    "IDR": 16250.0,
    "PHP": 58.3,
    "KHR": 4100.0,
    "LAK": 21700.0,
    "MMK": 2100.0,
    "BND": 1.35,
    "HKD": 7.81,
    "KRW": 1380.0,
    "JPY": 157.0,
}

CURRENCY_NAMES: dict[str, str] = {
    "USD": "United States Dollar",
    "EUR": "Euro",
    "GBP": "Pound Sterling",
    "AUD": "Australian Dollar",
    "VND": "Vietnamese Dong",
    "THB": "Thai Baht",
    "SGD": "Singapore Dollar",
    "MYR": "Malaysian Ringgit",
    "IDR": "Indonesian Rupiah",
    "PHP": "Philippine Peso",
    "KHR": "Cambodian Riel",
    "LAK": "Lao Kip",
    "MMK": "Myanmar Kyat",
    "BND": "Brunei Dollar",
    "HKD": "Hong Kong Dollar",
    "KRW": "South Korean Won",
    "JPY": "Japanese Yen",
}

# Seed-country name (as in countries.py) → its ISO 4217 code.
# Timor-Leste uses the US dollar as its official currency.
COUNTRY_CURRENCY: dict[str, str] = {
    "Vietnam": "VND",
    "Thailand": "THB",
    "Singapore": "SGD",
    "Malaysia": "MYR",
    "Indonesia": "IDR",
    "Philippines": "PHP",
    "Cambodia": "KHR",
    "Laos": "LAK",
    "Myanmar": "MMK",
    "Brunei": "BND",
    "Timor-Leste": "USD",
    "Hong Kong": "HKD",
    "South Korea": "KRW",
    "Japan": "JPY",
}

# ── Import-time validation (fail loudly on a typo, per the seed-data convention) ──
_country_names = {c["name"] for c in COUNTRIES}
_missing = _country_names - COUNTRY_CURRENCY.keys()
if _missing:
    raise ValueError(f"COUNTRY_CURRENCY is missing entries for: {sorted(_missing)}")

_unknown_codes = set(COUNTRY_CURRENCY.values()) - RATES.keys()
if _unknown_codes:
    raise ValueError(
        f"COUNTRY_CURRENCY maps to codes absent from RATES: {sorted(_unknown_codes)}"
    )

_unnamed = RATES.keys() - CURRENCY_NAMES.keys()
if _unnamed:
    raise ValueError(
        f"RATES codes missing a name in CURRENCY_NAMES: {sorted(_unnamed)}"
    )
