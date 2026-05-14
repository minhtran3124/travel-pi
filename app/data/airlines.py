"""Seed list of airlines used by the deterministic flight generator."""

AIRLINES: list[dict[str, str]] = [
    {"code": "VN", "name": "Vietnam Airlines"},
    {"code": "VJ", "name": "VietJet Air"},
    {"code": "QH", "name": "Bamboo Airways"},
    {"code": "OZ", "name": "Asiana Airlines"},
    {"code": "KE", "name": "Korean Air"},
    {"code": "SQ", "name": "Singapore Airlines"},
    {"code": "TG", "name": "Thai Airways"},
]

# Brand accent colors for the airline badge on the flight board.
# Presentation only — evocative, not official brand specs.
AIRLINE_COLORS: dict[str, str] = {
    "VN": "#0a3d91",  # Vietnam Airlines — blue
    "VJ": "#e30613",  # VietJet Air — red
    "QH": "#00843d",  # Bamboo Airways — green
    "OZ": "#d4002a",  # Asiana Airlines — red
    "KE": "#0067a3",  # Korean Air — sky blue
    "SQ": "#1d2d5c",  # Singapore Airlines — navy
    "TG": "#5b2d8e",  # Thai Airways — purple
}

# Fallback color for any airline code without an explicit brand color.
AIRLINE_COLOR_DEFAULT = "#444b55"
