"""Canonical country list.

The 14 countries currently in use across the seed data — every value that
appears in the ``country`` field of ``cities.py`` and as a key of
``COUNTRY_TIPS`` in ``tips.py``. Keep this list in sync when adding cities
or country tips for a new country.

Each entry has the country ``name``, its ISO 3166-1 alpha-2 ``code``, and
the broad ``region`` it belongs to. Order matches ``cities.py``: Southeast
Asia first, then East Asia.
"""

COUNTRIES: list[dict] = [
    # ── Southeast Asia ────────────────────────────────────────────────────────
    {
        "name": "Vietnam",
        "code": "VN",
        "region": "Southeast Asia",
        "latitude": 14.0583,
        "longitude": 108.2772,
    },
    {
        "name": "Thailand",
        "code": "TH",
        "region": "Southeast Asia",
        "latitude": 15.8700,
        "longitude": 100.9925,
    },
    {
        "name": "Singapore",
        "code": "SG",
        "region": "Southeast Asia",
        "latitude": 1.3521,
        "longitude": 103.8198,
    },
    {
        "name": "Malaysia",
        "code": "MY",
        "region": "Southeast Asia",
        "latitude": 4.2105,
        "longitude": 101.6964,
    },
    {
        "name": "Indonesia",
        "code": "ID",
        "region": "Southeast Asia",
        "latitude": -0.7893,
        "longitude": 113.9213,
    },
    {
        "name": "Philippines",
        "code": "PH",
        "region": "Southeast Asia",
        "latitude": 12.8797,
        "longitude": 121.7740,
    },
    {
        "name": "Cambodia",
        "code": "KH",
        "region": "Southeast Asia",
        "latitude": 12.5657,
        "longitude": 104.9910,
    },
    {
        "name": "Laos",
        "code": "LA",
        "region": "Southeast Asia",
        "latitude": 19.8523,
        "longitude": 102.4955,
    },
    {
        "name": "Myanmar",
        "code": "MM",
        "region": "Southeast Asia",
        "latitude": 21.9162,
        "longitude": 95.9560,
    },
    {
        "name": "Brunei",
        "code": "BN",
        "region": "Southeast Asia",
        "latitude": 4.5353,
        "longitude": 114.7277,
    },
    {
        "name": "Timor-Leste",
        "code": "TL",
        "region": "Southeast Asia",
        "latitude": -8.8383,
        "longitude": 125.9181,
    },
    # ── East Asia ─────────────────────────────────────────────────────────────
    {
        "name": "Hong Kong",
        "code": "HK",
        "region": "East Asia",
        "latitude": 22.3193,
        "longitude": 114.1694,
    },
    {
        "name": "South Korea",
        "code": "KR",
        "region": "East Asia",
        "latitude": 37.2871,
        "longitude": 127.0065,
    },
    {
        "name": "Japan",
        "code": "JP",
        "region": "East Asia",
        "latitude": 36.2048,
        "longitude": 138.2529,
    },
]
