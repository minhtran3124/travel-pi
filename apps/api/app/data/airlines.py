"""Seed airlines."""

AIRLINES: list[dict[str, str]] = [
    {"code": "VN", "name": "Vietnam Airlines"},
    {"code": "VJ", "name": "VietJet Air"},
    {"code": "QH", "name": "Bamboo Airways"},
    {"code": "OZ", "name": "Asiana Airlines"},
    {"code": "KE", "name": "Korean Air"},
    {"code": "SQ", "name": "Singapore Airlines"},
    {"code": "TG", "name": "Thai Airways"},
    {"code": "JL", "name": "Japan Airlines"},
    {"code": "NH", "name": "All Nippon Airways"},
    {"code": "BR", "name": "EVA Airways Corporation"},
    {"code": "MU", "name": "China Eastern Airlines"},
    {"code": "AF", "name": "Air France"},
    {"code": "BA", "name": "British Airways"},
    {"code": "TP", "name": "TAP Air Portugal"},
    {"code": "AZ", "name": "ITA Airways"},
    {"code": "QF", "name": "Qantas Airways"},
    {"code": "EK", "name": "Emirates"},
    {"code": "TK", "name": "Turkish Airlines"},
]

# Presentation-only accent colors; evocative, not official brand specs.
AIRLINE_COLORS: dict[str, str] = {
    "VN": "#0a3d91",
    "VJ": "#e30613",
    "QH": "#00843d",
    "OZ": "#d4002a",
    "KE": "#0067a3",
    "SQ": "#1d2d5c",
    "TG": "#5b2d8e",
    "JL": "#cc0000",
    "NH": "#13448f",
    "BR": "#006b3f",
    "MU": "#c8102e",
    "AF": "#002157",
    "BA": "#075aaa",
    "TP": "#e4002b",
    "AZ": "#1b3664",
    "QF": "#e40000",
    "EK": "#d71921",
    "TK": "#c70a0c",
}

AIRLINE_COLOR_DEFAULT = "#444b55"
