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
    {"name": "Vietnam", "code": "VN", "region": "Southeast Asia"},
    {"name": "Thailand", "code": "TH", "region": "Southeast Asia"},
    {"name": "Singapore", "code": "SG", "region": "Southeast Asia"},
    {"name": "Malaysia", "code": "MY", "region": "Southeast Asia"},
    {"name": "Indonesia", "code": "ID", "region": "Southeast Asia"},
    {"name": "Philippines", "code": "PH", "region": "Southeast Asia"},
    {"name": "Cambodia", "code": "KH", "region": "Southeast Asia"},
    {"name": "Laos", "code": "LA", "region": "Southeast Asia"},
    {"name": "Myanmar", "code": "MM", "region": "Southeast Asia"},
    {"name": "Brunei", "code": "BN", "region": "Southeast Asia"},
    {"name": "Timor-Leste", "code": "TL", "region": "Southeast Asia"},
    # ── East Asia ─────────────────────────────────────────────────────────────
    {"name": "Hong Kong", "code": "HK", "region": "East Asia"},
    {"name": "South Korea", "code": "KR", "region": "East Asia"},
    {"name": "Japan", "code": "JP", "region": "East Asia"},
]
