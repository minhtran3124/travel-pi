"""Static, country-keyed entry-requirement guidance (mock seed data).

This is **general, illustrative guidance** — real visa rules depend on the
traveller's nationality and change often. The API surfaces a ``disclaimer``
on every response. Keyed by destination country, like ``tips.py``'s
``COUNTRY_TIPS``; ``countries.py`` is the single source of truth for the
country list and the guard at the bottom rejects any drift.

Each record:
  * ``visa_free_days``           — typical visa-free stay for many nationalities
                                   (``0`` = a visa is generally required).
  * ``visa_on_arrival``          — visa-on-arrival is commonly available.
  * ``e_visa``                   — an online / e-visa option exists.
  * ``passport_validity_months`` — months of validity typically required beyond
                                   entry (``0`` = "valid for the duration of stay").
  * ``summary``                  — one natural-language sentence the agent can quote.
"""

from app.data.countries import COUNTRIES

COUNTRY_VISA: dict[str, dict] = {
    "Vietnam": {
        "visa_free_days": 45,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many nationalities get 45 days visa-free; others can apply for a 90-day e-visa online before arrival.",
    },
    "Thailand": {
        "visa_free_days": 60,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many passports enter visa-free for up to 60 days; visa-on-arrival and an e-visa are available for others.",
    },
    "Singapore": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 6,
        "summary": "Most nationalities enter visa-free for 30–90 days; everyone must submit the free SG Arrival Card online before arrival.",
    },
    "Malaysia": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many passports get up to 90 days visa-free; complete the Malaysia Digital Arrival Card (MDAC) before you travel.",
    },
    "Indonesia": {
        "visa_free_days": 30,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "A 30-day visa-on-arrival (extendable once) is available to many nationalities and can be bought online as an e-VoA.",
    },
    "Philippines": {
        "visa_free_days": 30,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many nationalities enter visa-free for 30 days; register via the eTravel system before arrival.",
    },
    "Cambodia": {
        "visa_free_days": 0,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Most visitors need a tourist visa, easily obtained on arrival or online as an e-visa before travel.",
    },
    "Laos": {
        "visa_free_days": 0,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Most visitors need a tourist visa, available on arrival or online as an e-visa.",
    },
    "Myanmar": {
        "visa_free_days": 0,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "A tourist e-visa is required in advance; check current travel advisories carefully before planning a trip.",
    },
    "Brunei": {
        "visa_free_days": 90,
        "visa_on_arrival": True,
        "e_visa": False,
        "passport_validity_months": 6,
        "summary": "Visa-free stays vary widely by nationality (14–90 days); visa-on-arrival is available for some passports.",
    },
    "Timor-Leste": {
        "visa_free_days": 0,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "A 30-day visa-on-arrival is available at Dili airport for most nationalities; an e-visa option also exists.",
    },
    "Hong Kong": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 1,
        "summary": "Most nationalities enter visa-free for 7–180 days (commonly 90); no advance application is needed.",
    },
    "South Korea": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many passports enter visa-free for up to 90 days; a K-ETA travel authorisation may be required before boarding.",
    },
    "Japan": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 0,
        "summary": "Many nationalities get a 90-day visa exemption for tourism; the passport need only be valid for the stay.",
    },
}

# ── Import-time validation (fail loudly on drift, per the seed-data convention) ──
_country_names = {c["name"] for c in COUNTRIES}
_missing = _country_names - COUNTRY_VISA.keys()
if _missing:
    raise ValueError(f"COUNTRY_VISA is missing entries for: {sorted(_missing)}")

_unknown = COUNTRY_VISA.keys() - _country_names
if _unknown:
    raise ValueError(
        f"COUNTRY_VISA references unknown countries: {sorted(_unknown)} "
        "— add them to app/data/countries.py"
    )
