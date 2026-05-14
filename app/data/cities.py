"""Canonical city list.

Merges every city that appears in ``airports.py`` or ``hotels.py``,
deduplicated. Each entry stores the city name, country, and the IATA
codes of all airports that serve the city (empty list for cities that
have hotel data but no seeded airport, e.g. Hoi An).

Order: Vietnam first (alphabetical), then the rest of Southeast Asia
alphabetical by country then city, then East Asia.

``countries.py`` is the single source of truth for the country list — the
consistency guard at the bottom of this file rejects any city whose
``country`` is not defined there.
"""

from app.data.countries import COUNTRIES as _COUNTRIES

CITIES: list[dict] = [
    # ── Vietnam ───────────────────────────────────────────────────────────────
    {
        "name": "Can Tho",
        "country": "Vietnam",
        "airport_codes": ["VCA"],
    },
    {
        "name": "Da Lat",
        "country": "Vietnam",
        "airport_codes": ["DLI"],
    },
    {
        "name": "Da Nang",
        "country": "Vietnam",
        "airport_codes": ["DAD"],
    },
    {
        "name": "Hai Phong",
        "country": "Vietnam",
        "airport_codes": ["HPH"],
    },
    {
        "name": "Hanoi",
        "country": "Vietnam",
        "airport_codes": ["HAN"],
    },
    {
        "name": "Ho Chi Minh City",
        "country": "Vietnam",
        "airport_codes": ["SGN"],
    },
    {
        "name": "Hoi An",
        "country": "Vietnam",
        "airport_codes": [],  # nearest airport: DAD (Da Nang)
    },
    {
        "name": "Hue",
        "country": "Vietnam",
        "airport_codes": ["HUI"],
    },
    {
        "name": "Nha Trang",
        "country": "Vietnam",
        "airport_codes": ["CXR"],
    },
    {
        "name": "Phu Quoc",
        "country": "Vietnam",
        "airport_codes": ["PQC"],
    },
    {
        "name": "Quy Nhon",
        "country": "Vietnam",
        "airport_codes": ["UIH"],
    },
    {
        "name": "Vinh",
        "country": "Vietnam",
        "airport_codes": ["VII"],
    },
    # ── Thailand ──────────────────────────────────────────────────────────────
    {
        "name": "Bangkok",
        "country": "Thailand",
        "airport_codes": ["BKK", "DMK"],
    },
    {
        "name": "Chiang Mai",
        "country": "Thailand",
        "airport_codes": ["CNX"],
    },
    {
        "name": "Hat Yai",
        "country": "Thailand",
        "airport_codes": ["HDY"],
    },
    {
        "name": "Koh Samui",
        "country": "Thailand",
        "airport_codes": ["USM"],
    },
    {
        "name": "Krabi",
        "country": "Thailand",
        "airport_codes": ["KBV"],
    },
    {
        "name": "Phuket",
        "country": "Thailand",
        "airport_codes": ["HKT"],
    },
    # ── Singapore ─────────────────────────────────────────────────────────────
    {
        "name": "Singapore",
        "country": "Singapore",
        "airport_codes": ["SIN"],
    },
    # ── Malaysia ──────────────────────────────────────────────────────────────
    {
        "name": "Johor Bahru",
        "country": "Malaysia",
        "airport_codes": ["JHB"],
    },
    {
        "name": "Kota Kinabalu",
        "country": "Malaysia",
        "airport_codes": ["BKI"],
    },
    {
        "name": "Kuala Lumpur",
        "country": "Malaysia",
        "airport_codes": ["KUL"],
    },
    {
        "name": "Kuching",
        "country": "Malaysia",
        "airport_codes": ["KCH"],
    },
    {
        "name": "Langkawi",
        "country": "Malaysia",
        "airport_codes": ["LGK"],
    },
    {
        "name": "Penang",
        "country": "Malaysia",
        "airport_codes": ["PEN"],
    },
    # ── Indonesia ─────────────────────────────────────────────────────────────
    {
        "name": "Bali",
        "country": "Indonesia",
        "airport_codes": ["DPS"],
    },
    {
        "name": "Balikpapan",
        "country": "Indonesia",
        "airport_codes": ["BPN"],
    },
    {
        "name": "Jakarta",
        "country": "Indonesia",
        "airport_codes": ["CGK"],
    },
    {
        "name": "Makassar",
        "country": "Indonesia",
        "airport_codes": ["UPG"],
    },
    {
        "name": "Medan",
        "country": "Indonesia",
        "airport_codes": ["KNO"],
    },
    {
        "name": "Surabaya",
        "country": "Indonesia",
        "airport_codes": ["SUB"],
    },
    # ── Philippines ───────────────────────────────────────────────────────────
    {
        "name": "Angeles",
        "country": "Philippines",
        "airport_codes": ["CRK"],
    },
    {
        "name": "Cebu",
        "country": "Philippines",
        "airport_codes": ["CEB"],
    },
    {
        "name": "Davao",
        "country": "Philippines",
        "airport_codes": ["DVO"],
    },
    {
        "name": "Kalibo (Boracay)",
        "country": "Philippines",
        "airport_codes": ["KLO"],
    },
    {
        "name": "Manila",
        "country": "Philippines",
        "airport_codes": ["MNL"],
    },
    {
        "name": "Puerto Princesa",
        "country": "Philippines",
        "airport_codes": ["PPS"],
    },
    # ── Cambodia ──────────────────────────────────────────────────────────────
    {
        "name": "Phnom Penh",
        "country": "Cambodia",
        "airport_codes": ["PNH"],
    },
    {
        "name": "Siem Reap",
        "country": "Cambodia",
        "airport_codes": ["REP"],
    },
    {
        "name": "Sihanoukville",
        "country": "Cambodia",
        "airport_codes": ["KOS"],
    },
    # ── Laos ──────────────────────────────────────────────────────────────────
    {
        "name": "Luang Prabang",
        "country": "Laos",
        "airport_codes": ["LPQ"],
    },
    {
        "name": "Vientiane",
        "country": "Laos",
        "airport_codes": ["VTE"],
    },
    # ── Myanmar ───────────────────────────────────────────────────────────────
    {
        "name": "Mandalay",
        "country": "Myanmar",
        "airport_codes": ["MDL"],
    },
    {
        "name": "Yangon",
        "country": "Myanmar",
        "airport_codes": ["RGN"],
    },
    # ── Brunei ────────────────────────────────────────────────────────────────
    {
        "name": "Bandar Seri Begawan",
        "country": "Brunei",
        "airport_codes": ["BWN"],
    },
    # ── Timor-Leste ───────────────────────────────────────────────────────────
    {
        "name": "Dili",
        "country": "Timor-Leste",
        "airport_codes": ["DIL"],
    },
    # ── East Asia ─────────────────────────────────────────────────────────────
    {
        "name": "Hong Kong",
        "country": "Hong Kong",
        "airport_codes": ["HKG"],
    },
    {
        "name": "Seoul",
        "country": "South Korea",
        "airport_codes": ["ICN"],
    },
    {
        "name": "Tokyo",
        "country": "Japan",
        "airport_codes": ["NRT"],
    },
]

# Consistency guard: every country named above must exist in countries.py,
# the single source of truth for the country list. A typo or a new country
# without a countries.py entry fails loudly at import time.
_VALID_COUNTRIES: set[str] = {c["name"] for c in _COUNTRIES}
for _city in CITIES:
    if _city["country"] not in _VALID_COUNTRIES:
        raise ValueError(
            f"cities.py: {_city['name']!r} uses unknown country "
            f"{_city['country']!r} — add it to app/data/countries.py"
        )
