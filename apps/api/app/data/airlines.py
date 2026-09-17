"""Seed airlines."""

AIRLINES: list[dict[str, str]] = [
    {"code": "VN", "name": "Vietnam Airlines"},
    {"code": "VJ", "name": "VietJet Air"},
    {"code": "QH", "name": "Bamboo Airways"},
    {"code": "OZ", "name": "Asiana Airlines"},
    {"code": "KE", "name": "Korean Air"},
    {"code": "SQ", "name": "Singapore Airlines"},
    {"code": "TG", "name": "Thai Airways"},
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
}

AIRLINE_COLOR_DEFAULT = "#444b55"
