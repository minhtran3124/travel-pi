"""Seed airports keyed by IATA code; ``country_code`` is filled from countries.py."""

from app.data.countries import COUNTRIES

AIRPORTS: dict[str, dict[str, str]] = {
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
    "SIN": {
        "name": "Singapore Changi Airport",
        "city": "Singapore",
        "country": "Singapore",
    },
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
    "BWN": {
        "name": "Brunei International Airport",
        "city": "Bandar Seri Begawan",
        "country": "Brunei",
    },
    "DIL": {
        "name": "Presidente Nicolau Lobato International Airport",
        "city": "Dili",
        "country": "Timor-Leste",
    },
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
    "KIX": {
        "name": "Kansai International Airport",
        "city": "Osaka",
        "country": "Japan",
    },
    "ITM": {
        "name": "Osaka Itami Airport",
        "city": "Osaka",
        "country": "Japan",
    },
    "FUK": {
        "name": "Fukuoka Airport",
        "city": "Fukuoka",
        "country": "Japan",
    },
    "CTS": {
        "name": "New Chitose Airport",
        "city": "Sapporo",
        "country": "Japan",
    },
    "PUS": {
        "name": "Gimhae International Airport",
        "city": "Busan",
        "country": "South Korea",
    },
    "CJU": {
        "name": "Jeju International Airport",
        "city": "Jeju",
        "country": "South Korea",
    },
    "TPE": {
        "name": "Taiwan Taoyuan International Airport",
        "city": "Taipei",
        "country": "Taiwan",
    },
    "TSA": {
        "name": "Taipei Songshan Airport",
        "city": "Taipei",
        "country": "Taiwan",
    },
    "PVG": {
        "name": "Shanghai Pudong International Airport",
        "city": "Shanghai",
        "country": "China",
    },
    "SHA": {
        "name": "Shanghai Hongqiao International Airport",
        "city": "Shanghai",
        "country": "China",
    },
    "PEK": {
        "name": "Beijing Capital International Airport",
        "city": "Beijing",
        "country": "China",
    },
    "PKX": {
        "name": "Beijing Daxing International Airport",
        "city": "Beijing",
        "country": "China",
    },
    "CAN": {
        "name": "Guangzhou Baiyun International Airport",
        "city": "Guangzhou",
        "country": "China",
    },
    "CDG": {
        "name": "Paris Charles de Gaulle Airport",
        "city": "Paris",
        "country": "France",
    },
    "ORY": {
        "name": "Paris Orly Airport",
        "city": "Paris",
        "country": "France",
    },
    "LHR": {
        "name": "London Heathrow Airport",
        "city": "London",
        "country": "United Kingdom",
    },
    "LGW": {
        "name": "London Gatwick Airport",
        "city": "London",
        "country": "United Kingdom",
    },
    "LIS": {
        "name": "Humberto Delgado Airport",
        "city": "Lisbon",
        "country": "Portugal",
    },
    "FCO": {
        "name": "Leonardo da Vinci-Fiumicino Airport",
        "city": "Rome",
        "country": "Italy",
    },
    "SYD": {
        "name": "Sydney Kingsford Smith Airport",
        "city": "Sydney",
        "country": "Australia",
    },
    "MEL": {
        "name": "Melbourne Airport",
        "city": "Melbourne",
        "country": "Australia",
    },
    "DXB": {
        "name": "Dubai International Airport",
        "city": "Dubai",
        "country": "United Arab Emirates",
    },
    "IST": {
        "name": "Istanbul Airport",
        "city": "Istanbul",
        "country": "Turkey",
    },
    "SAW": {
        "name": "Istanbul Sabiha Gökçen International Airport",
        "city": "Istanbul",
        "country": "Turkey",
    },
    "JFK": {
        "name": "John F. Kennedy International Airport",
        "city": "New York",
        "country": "United States",
    },
    "EWR": {
        "name": "Newark Liberty International Airport",
        "city": "New York",
        "country": "United States",
    },
    "LAX": {
        "name": "Los Angeles International Airport",
        "city": "Los Angeles",
        "country": "United States",
    },
}

# An airport naming a country absent from countries.py raises KeyError at import.
_COUNTRY_CODE: dict[str, str] = {c["name"]: c["code"] for c in COUNTRIES}

for _info in AIRPORTS.values():
    _info["country_code"] = _COUNTRY_CODE[_info["country"]]
