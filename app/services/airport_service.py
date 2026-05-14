"""Airport lookup over the in-memory seed data."""

from app.data.airports import AIRPORTS
from app.schemas.airport import Airport

_AIRPORTS: list[Airport] = [
    Airport(code=code, name=info["name"], city=info["city"], country=info["country"])
    for code, info in AIRPORTS.items()
]
_BY_CODE: dict[str, Airport] = {airport.code: airport for airport in _AIRPORTS}


def list_airports() -> list[Airport]:
    """Return the supported airports as a list of ``Airport`` objects."""
    return _AIRPORTS


def get_airport(code: str) -> Airport | None:
    """Return the airport for an IATA ``code``, or ``None`` if unknown.

    Used by the web pages to show a friendly city / name next to the raw
    3-letter code. Flights can be generated for any code, so callers must
    handle a ``None`` result (just show the bare code in that case).
    """
    return _BY_CODE.get(code.upper())
