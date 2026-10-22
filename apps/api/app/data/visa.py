"""Illustrative (mock) entry-requirement guidance keyed by destination country; not real visa rules."""

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
    "China": {
        "visa_free_days": 30,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 6,
        "summary": "Many passports (much of Europe, Japan, Korea, Australia and others) now enter visa-free for up to 30 days, and a 240-hour visa-free transit covers more; Vietnamese passport holders need a visa (Hainan Island aside). (checked 2026-09)",
    },
    "Taiwan": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many passports (US, EU, UK, Japan, Korea and others) enter visa-free for up to 90 days; Vietnamese passport holders need a visa or, if they hold a qualifying visa from certain countries, an online Travel Authorization Certificate. (checked 2026-09)",
    },
    "France": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 3,
        "summary": "Schengen rules: many passports stay visa-free for 90 days in any 180; Vietnamese passport holders need a Schengen visa. (checked 2026-09)",
    },
    "United Kingdom": {
        "visa_free_days": 180,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 0,
        "summary": "Many passports visit visa-free for up to 6 months but must get an online Electronic Travel Authorisation (ETA) first; Vietnamese passport holders need a Standard Visitor visa. (checked 2026-09)",
    },
    "Portugal": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 3,
        "summary": "Schengen rules: many passports stay visa-free for 90 days in any 180; Vietnamese passport holders need a Schengen visa. (checked 2026-09)",
    },
    "Italy": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": False,
        "passport_validity_months": 3,
        "summary": "Schengen rules: many passports stay visa-free for 90 days in any 180; Vietnamese passport holders need a Schengen visa. (checked 2026-09)",
    },
    "Australia": {
        "visa_free_days": 0,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Almost every visitor needs an electronic authorisation (ETA or eVisitor) or a visa before travel; Vietnamese passport holders apply online for a Visitor (subclass 600) visa. (checked 2026-09)",
    },
    "United Arab Emirates": {
        "visa_free_days": 30,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many passports get a free 30- or 90-day entry stamp on arrival; Vietnamese passport holders need a visa arranged in advance online through an airline, hotel or licensed sponsor. (checked 2026-09)",
    },
    "Turkey": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Many passports enter visa-free for 90 days in any 180, and others use an online e-Visa; Vietnamese passport holders can use the e-Visa only in some cases (for example with a valid Schengen, UK or US visa), otherwise they need a consular visa. (checked 2026-09)",
    },
    "United States": {
        "visa_free_days": 90,
        "visa_on_arrival": False,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": "Visa Waiver Program passports visit for up to 90 days with an approved ESTA; Vietnamese passport holders need a B1/B2 visitor visa with an embassy interview. (checked 2026-09)",
    },
}

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
