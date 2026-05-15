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
        "latitude": 10.0379,
        "longitude": 105.7869,
    },
    {
        "name": "Da Lat",
        "country": "Vietnam",
        "airport_codes": ["DLI"],
        "latitude": 11.9404,
        "longitude": 108.4422,
    },
    {
        "name": "Da Nang",
        "country": "Vietnam",
        "airport_codes": ["DAD"],
        "latitude": 16.0680,
        "longitude": 108.2206,
    },
    {
        "name": "Hai Phong",
        "country": "Vietnam",
        "airport_codes": ["HPH"],
        "latitude": 20.8445,
        "longitude": 106.6881,
    },
    {
        "name": "Hanoi",
        "country": "Vietnam",
        "airport_codes": ["HAN"],
        "latitude": 21.0285,
        "longitude": 105.8542,
    },
    {
        "name": "Ho Chi Minh City",
        "country": "Vietnam",
        "airport_codes": ["SGN"],
        "latitude": 10.7769,
        "longitude": 106.6964,
    },
    {
        "name": "Hoi An",
        "country": "Vietnam",
        "airport_codes": [],  # nearest airport: DAD (Da Nang)
        "latitude": 15.8801,
        "longitude": 108.3298,
    },
    {
        "name": "Hue",
        "country": "Vietnam",
        "airport_codes": ["HUI"],
        "latitude": 16.4637,
        "longitude": 107.5909,
    },
    {
        "name": "Nha Trang",
        "country": "Vietnam",
        "airport_codes": ["CXR"],
        "latitude": 12.2388,
        "longitude": 109.1967,
    },
    {
        "name": "Phu Quoc",
        "country": "Vietnam",
        "airport_codes": ["PQC"],
        "latitude": 10.1915,
        "longitude": 103.9847,
    },
    {
        "name": "Quy Nhon",
        "country": "Vietnam",
        "airport_codes": ["UIH"],
        "latitude": 13.7794,
        "longitude": 109.2287,
    },
    {
        "name": "Vinh",
        "country": "Vietnam",
        "airport_codes": ["VII"],
        "latitude": 18.6760,
        "longitude": 105.6888,
    },
    # ── Thailand ──────────────────────────────────────────────────────────────
    {
        "name": "Bangkok",
        "country": "Thailand",
        "airport_codes": ["BKK", "DMK"],
        "latitude": 13.7563,
        "longitude": 100.5018,
    },
    {
        "name": "Chiang Mai",
        "country": "Thailand",
        "airport_codes": ["CNX"],
        "latitude": 18.7883,
        "longitude": 98.9853,
    },
    {
        "name": "Hat Yai",
        "country": "Thailand",
        "airport_codes": ["HDY"],
        "latitude": 7.0097,
        "longitude": 100.4733,
    },
    {
        "name": "Koh Samui",
        "country": "Thailand",
        "airport_codes": ["USM"],
        "latitude": 8.9575,
        "longitude": 100.2869,
    },
    {
        "name": "Krabi",
        "country": "Thailand",
        "airport_codes": ["KBV"],
        "latitude": 8.0863,
        "longitude": 98.9063,
    },
    {
        "name": "Phuket",
        "country": "Thailand",
        "airport_codes": ["HKT"],
        "latitude": 7.8804,
        "longitude": 98.3923,
    },
    # ── Singapore ─────────────────────────────────────────────────────────────
    {
        "name": "Singapore",
        "country": "Singapore",
        "airport_codes": ["SIN"],
        "latitude": 1.3521,
        "longitude": 103.8198,
    },
    # ── Malaysia ──────────────────────────────────────────────────────────────
    {
        "name": "Johor Bahru",
        "country": "Malaysia",
        "airport_codes": ["JHB"],
        "latitude": 1.4854,
        "longitude": 103.7618,
    },
    {
        "name": "Kota Kinabalu",
        "country": "Malaysia",
        "airport_codes": ["BKI"],
        "latitude": 5.3520,
        "longitude": 118.7339,
    },
    {
        "name": "Kuala Lumpur",
        "country": "Malaysia",
        "airport_codes": ["KUL"],
        "latitude": 3.1390,
        "longitude": 101.6869,
    },
    {
        "name": "Kuching",
        "country": "Malaysia",
        "airport_codes": ["KCH"],
        "latitude": 1.5241,
        "longitude": 110.3592,
    },
    {
        "name": "Langkawi",
        "country": "Malaysia",
        "airport_codes": ["LGK"],
        "latitude": 6.3520,
        "longitude": 99.8333,
    },
    {
        "name": "Penang",
        "country": "Malaysia",
        "airport_codes": ["PEN"],
        "latitude": 5.4164,
        "longitude": 100.3327,
    },
    # ── Indonesia ─────────────────────────────────────────────────────────────
    {
        "name": "Bali",
        "country": "Indonesia",
        "airport_codes": ["DPS"],
        "latitude": -8.6705,
        "longitude": 115.2126,
    },
    {
        "name": "Balikpapan",
        "country": "Indonesia",
        "airport_codes": ["BPN"],
        "latitude": -1.2656,
        "longitude": 116.8331,
    },
    {
        "name": "Jakarta",
        "country": "Indonesia",
        "airport_codes": ["CGK"],
        "latitude": -6.2088,
        "longitude": 106.8456,
    },
    {
        "name": "Makassar",
        "country": "Indonesia",
        "airport_codes": ["UPG"],
        "latitude": -5.1477,
        "longitude": 119.4327,
    },
    {
        "name": "Medan",
        "country": "Indonesia",
        "airport_codes": ["KNO"],
        "latitude": 3.5952,
        "longitude": 98.6722,
    },
    {
        "name": "Surabaya",
        "country": "Indonesia",
        "airport_codes": ["SUB"],
        "latitude": -7.2505,
        "longitude": 112.7508,
    },
    # ── Philippines ───────────────────────────────────────────────────────────
    {
        "name": "Angeles",
        "country": "Philippines",
        "airport_codes": ["CRK"],
        "latitude": 15.1605,
        "longitude": 120.5898,
    },
    {
        "name": "Cebu",
        "country": "Philippines",
        "airport_codes": ["CEB"],
        "latitude": 10.3157,
        "longitude": 123.8854,
    },
    {
        "name": "Davao",
        "country": "Philippines",
        "airport_codes": ["DVO"],
        "latitude": 7.1315,
        "longitude": 125.6521,
    },
    {
        "name": "Kalibo (Boracay)",
        "country": "Philippines",
        "airport_codes": ["KLO"],
        "latitude": 11.9820,
        "longitude": 121.9760,
    },
    {
        "name": "Manila",
        "country": "Philippines",
        "airport_codes": ["MNL"],
        "latitude": 14.5995,
        "longitude": 120.9842,
    },
    {
        "name": "Puerto Princesa",
        "country": "Philippines",
        "airport_codes": ["PPS"],
        "latitude": 9.7424,
        "longitude": 118.7338,
    },
    # ── Cambodia ──────────────────────────────────────────────────────────────
    {
        "name": "Phnom Penh",
        "country": "Cambodia",
        "airport_codes": ["PNH"],
        "latitude": 11.5564,
        "longitude": 104.9282,
    },
    {
        "name": "Siem Reap",
        "country": "Cambodia",
        "airport_codes": ["REP"],
        "latitude": 13.3671,
        "longitude": 103.8448,
    },
    {
        "name": "Sihanoukville",
        "country": "Cambodia",
        "airport_codes": ["KOS"],
        "latitude": 10.6282,
        "longitude": 103.5197,
    },
    # ── Laos ──────────────────────────────────────────────────────────────────
    {
        "name": "Luang Prabang",
        "country": "Laos",
        "airport_codes": ["LPQ"],
        "latitude": 19.8845,
        "longitude": 102.1348,
    },
    {
        "name": "Vientiane",
        "country": "Laos",
        "airport_codes": ["VTE"],
        "latitude": 17.9757,
        "longitude": 102.6331,
    },
    # ── Myanmar ───────────────────────────────────────────────────────────────
    {
        "name": "Mandalay",
        "country": "Myanmar",
        "airport_codes": ["MDL"],
        "latitude": 21.9748,
        "longitude": 96.0836,
    },
    {
        "name": "Yangon",
        "country": "Myanmar",
        "airport_codes": ["RGN"],
        "latitude": 16.8661,
        "longitude": 96.1951,
    },
    # ── Brunei ────────────────────────────────────────────────────────────────
    {
        "name": "Bandar Seri Begawan",
        "country": "Brunei",
        "airport_codes": ["BWN"],
        "latitude": 4.8804,
        "longitude": 114.9355,
    },
    # ── Timor-Leste ───────────────────────────────────────────────────────────
    {
        "name": "Dili",
        "country": "Timor-Leste",
        "airport_codes": ["DIL"],
        "latitude": -8.5563,
        "longitude": 125.5827,
    },
    # ── East Asia ─────────────────────────────────────────────────────────────
    {
        "name": "Hong Kong",
        "country": "Hong Kong",
        "airport_codes": ["HKG"],
        "latitude": 22.3193,
        "longitude": 114.1694,
    },
    {
        "name": "Seoul",
        "country": "South Korea",
        "airport_codes": ["ICN"],
        "latitude": 37.5665,
        "longitude": 126.9780,
    },
    {
        "name": "Tokyo",
        "country": "Japan",
        "airport_codes": ["NRT"],
        "latitude": 35.6762,
        "longitude": 139.6503,
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
