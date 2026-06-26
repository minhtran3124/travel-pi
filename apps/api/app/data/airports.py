"""Seed list of supported airports, keyed by IATA code.

Covers all of Southeast Asia (Vietnam, Thailand, Singapore, Malaysia,
Indonesia, the Philippines, Cambodia, Laos, Myanmar, Brunei, Timor-Leste)
plus a few East Asian hubs kept from the original seed. Each entry carries
the airport ``name``, its ``city``, its ``country``, and the ISO
``country_code`` — the last one is filled in automatically from
``countries.py`` so the country list stays the single source of truth.
"""

from app.data.countries import COUNTRIES

AIRPORTS: dict[str, dict[str, str]] = {
    # --- Vietnam ---
    "DAD": {
        "name": "Da Nang International Airport",
        "city": "Da Nang",
        "country": "Vietnam",
    },
    "SGN": {
        "name": "Tan Son Nhat International Airport",
        "city": "Ho Chi Minh City",
        "country": "Vietnam",
    },
    "HAN": {
        "name": "Noi Bai International Airport",
        "city": "Hanoi",
        "country": "Vietnam",
    },
    "PQC": {
        "name": "Phu Quoc International Airport",
        "city": "Phu Quoc",
        "country": "Vietnam",
    },
    "CXR": {
        "name": "Cam Ranh International Airport",
        "city": "Nha Trang",
        "country": "Vietnam",
    },
    "HPH": {
        "name": "Cat Bi International Airport",
        "city": "Hai Phong",
        "country": "Vietnam",
    },
    "VCA": {
        "name": "Can Tho International Airport",
        "city": "Can Tho",
        "country": "Vietnam",
    },
    "DLI": {
        "name": "Lien Khuong Airport",
        "city": "Da Lat",
        "country": "Vietnam",
    },
    "HUI": {
        "name": "Phu Bai International Airport",
        "city": "Hue",
        "country": "Vietnam",
    },
    "VII": {
        "name": "Vinh International Airport",
        "city": "Vinh",
        "country": "Vietnam",
    },
    "UIH": {
        "name": "Phu Cat Airport",
        "city": "Quy Nhon",
        "country": "Vietnam",
    },
    # --- Thailand ---
    "BKK": {
        "name": "Suvarnabhumi Airport",
        "city": "Bangkok",
        "country": "Thailand",
    },
    "DMK": {
        "name": "Don Mueang International Airport",
        "city": "Bangkok",
        "country": "Thailand",
    },
    "HKT": {
        "name": "Phuket International Airport",
        "city": "Phuket",
        "country": "Thailand",
    },
    "CNX": {
        "name": "Chiang Mai International Airport",
        "city": "Chiang Mai",
        "country": "Thailand",
    },
    "USM": {
        "name": "Samui Airport",
        "city": "Koh Samui",
        "country": "Thailand",
    },
    "KBV": {
        "name": "Krabi International Airport",
        "city": "Krabi",
        "country": "Thailand",
    },
    "HDY": {
        "name": "Hat Yai International Airport",
        "city": "Hat Yai",
        "country": "Thailand",
    },
    # --- Singapore ---
    "SIN": {
        "name": "Singapore Changi Airport",
        "city": "Singapore",
        "country": "Singapore",
    },
    # --- Malaysia ---
    "KUL": {
        "name": "Kuala Lumpur International Airport",
        "city": "Kuala Lumpur",
        "country": "Malaysia",
    },
    "PEN": {
        "name": "Penang International Airport",
        "city": "Penang",
        "country": "Malaysia",
    },
    "BKI": {
        "name": "Kota Kinabalu International Airport",
        "city": "Kota Kinabalu",
        "country": "Malaysia",
    },
    "LGK": {
        "name": "Langkawi International Airport",
        "city": "Langkawi",
        "country": "Malaysia",
    },
    "KCH": {
        "name": "Kuching International Airport",
        "city": "Kuching",
        "country": "Malaysia",
    },
    "JHB": {
        "name": "Senai International Airport",
        "city": "Johor Bahru",
        "country": "Malaysia",
    },
    # --- Indonesia ---
    "CGK": {
        "name": "Soekarno-Hatta International Airport",
        "city": "Jakarta",
        "country": "Indonesia",
    },
    "DPS": {
        "name": "Ngurah Rai International Airport",
        "city": "Bali",
        "country": "Indonesia",
    },
    "SUB": {
        "name": "Juanda International Airport",
        "city": "Surabaya",
        "country": "Indonesia",
    },
    "KNO": {
        "name": "Kualanamu International Airport",
        "city": "Medan",
        "country": "Indonesia",
    },
    "UPG": {
        "name": "Sultan Hasanuddin International Airport",
        "city": "Makassar",
        "country": "Indonesia",
    },
    "BPN": {
        "name": "Sultan Aji Muhammad Sulaiman Sepinggan Airport",
        "city": "Balikpapan",
        "country": "Indonesia",
    },
    # --- Philippines ---
    "MNL": {
        "name": "Ninoy Aquino International Airport",
        "city": "Manila",
        "country": "Philippines",
    },
    "CEB": {
        "name": "Mactan-Cebu International Airport",
        "city": "Cebu",
        "country": "Philippines",
    },
    "DVO": {
        "name": "Francisco Bangoy International Airport",
        "city": "Davao",
        "country": "Philippines",
    },
    "CRK": {
        "name": "Clark International Airport",
        "city": "Angeles",
        "country": "Philippines",
    },
    "PPS": {
        "name": "Puerto Princesa International Airport",
        "city": "Puerto Princesa",
        "country": "Philippines",
    },
    "KLO": {
        "name": "Kalibo International Airport",
        "city": "Kalibo (Boracay)",
        "country": "Philippines",
    },
    # --- Cambodia ---
    "PNH": {
        "name": "Phnom Penh International Airport",
        "city": "Phnom Penh",
        "country": "Cambodia",
    },
    "REP": {
        "name": "Siem Reap International Airport",
        "city": "Siem Reap",
        "country": "Cambodia",
    },
    "KOS": {
        "name": "Sihanouk International Airport",
        "city": "Sihanoukville",
        "country": "Cambodia",
    },
    # --- Laos ---
    "VTE": {
        "name": "Wattay International Airport",
        "city": "Vientiane",
        "country": "Laos",
    },
    "LPQ": {
        "name": "Luang Prabang International Airport",
        "city": "Luang Prabang",
        "country": "Laos",
    },
    # --- Myanmar ---
    "RGN": {
        "name": "Yangon International Airport",
        "city": "Yangon",
        "country": "Myanmar",
    },
    "MDL": {
        "name": "Mandalay International Airport",
        "city": "Mandalay",
        "country": "Myanmar",
    },
    # --- Brunei ---
    "BWN": {
        "name": "Brunei International Airport",
        "city": "Bandar Seri Begawan",
        "country": "Brunei",
    },
    # --- Timor-Leste ---
    "DIL": {
        "name": "Presidente Nicolau Lobato International Airport",
        "city": "Dili",
        "country": "Timor-Leste",
    },
    # --- East Asia (non-SEA hubs, kept from the original seed) ---
    "ICN": {
        "name": "Incheon International Airport",
        "city": "Seoul",
        "country": "South Korea",
    },
    "NRT": {
        "name": "Narita International Airport",
        "city": "Tokyo",
        "country": "Japan",
    },
    "HKG": {
        "name": "Hong Kong International Airport",
        "city": "Hong Kong",
        "country": "Hong Kong",
    },
}

# Map each airport's country name to its ISO code via the canonical country
# list. The dict lookup also acts as a consistency guard: if an airport
# names a country that is missing from ``countries.py``, this raises a
# KeyError at import time instead of silently drifting out of sync.
_COUNTRY_CODE: dict[str, str] = {c["name"]: c["code"] for c in COUNTRIES}

for _info in AIRPORTS.values():
    _info["country_code"] = _COUNTRY_CODE[_info["country"]]
