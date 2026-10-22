"""Flight information board (FIDS) builder."""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.airline import AIRLINE_COLOR_DEFAULT, AirlineRepository
from app.schemas.airport import Airport
from app.schemas.flight import Flight
from app.services.airport_service import AirportService
from app.services.flight_service import FlightService

# 10 x 2 = ~20 rows, a realistic board length.
ROUTES_PER_BOARD = 10
FLIGHTS_PER_ROUTE = 2

# A flight counts as "Boarding" once it is within this window of departure.
BOARDING_WINDOW = timedelta(minutes=40)

ARRIVALS = "arrivals"
DEPARTURES = "departures"
_VALID_MODES = (ARRIVALS, DEPARTURES)


@dataclass
class BoardRow:
    """One line on the flight board."""

    scheduled: datetime  # STA (arrivals) or STD (departures)
    estimated: datetime | None  # ETA / ETD — None means "no change"
    airport: Airport | None  # the "From" (arrivals) or "To" (departures) airport
    airport_code: str  # raw code, shown as fallback if `airport` is None
    airline_code: str
    airline_name: str
    airline_color: str  # brand accent color for the airline badge
    flight_number: str  # display form with a space, e.g. "VJ 301"
    flight_id: str  # links to the flight detail page
    status: str  # display label, e.g. "Landed"
    status_kind: str  # landed | ontime | estimated | delayed | boarding | departed


def _hash(value: str) -> int:
    """Stable integer hash of a string (so the board is deterministic)."""
    return int(hashlib.md5(value.encode()).hexdigest(), 16)


def _punctuality_offset(digest: int) -> int:
    """Deterministic minutes offset for a flight: delayed (+), early (-), or 0."""
    bucket = digest % 4
    if bucket == 0:
        return 10 + (digest // 7) % 35  # delayed: +10..+44 min
    if bucket == 1:
        return -(1 + (digest // 11) % 10)  # early: -1..-10 min
    return 0  # on time


def _status_for(mode: str, offset: int, actual: datetime, now: datetime):
    """Status from timing; a still-future flight is never Landed/Departed/Boarding."""
    if actual <= now:
        return ("landed", "Landed") if mode == ARRIVALS else ("departed", "Departed")
    if offset > 0:
        return "delayed", "Delayed"
    if mode == DEPARTURES and actual - now <= BOARDING_WINDOW:
        return "boarding", "Boarding"
    if offset < 0:
        return "estimated", "Estimated"
    return "ontime", "On time"


class BoardService:
    """Flight information board (FIDS) builder."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._airline = AirlineRepository(session)

    def _make_row(self, flight: Flight, mode: str, now: datetime) -> BoardRow:
        """Turn a generated ``Flight`` into a board row for the given mode."""
        digest = _hash(flight.id)
        offset = _punctuality_offset(digest)

        # Arrivals are sorted/shown by arrival time; departures by departure time.
        scheduled = flight.arrival_time if mode == ARRIVALS else flight.departure_time
        # The expected real time, after applying the (deterministic) punctuality.
        actual = scheduled + timedelta(minutes=offset)

        kind, status = _status_for(mode, offset, actual, now)
        # The yellow "Estimated" column only shows a time when it actually changed.
        estimated = actual if offset != 0 else None

        # The "other" airport: where the flight came from / is going to.
        other_code = flight.origin if mode == ARRIVALS else flight.destination
        airline_code = flight.airline.code
        # "VN523" -> "VN 523"
        flight_number = (
            f"{airline_code} {flight.flight_number.removeprefix(airline_code)}"
        )

        return BoardRow(
            scheduled=scheduled,
            estimated=estimated,
            airport=AirportService(self._session).get_airport(other_code),
            airport_code=other_code,
            airline_code=airline_code,
            airline_name=flight.airline.name,
            airline_color=self._airline.color(airline_code) or AIRLINE_COLOR_DEFAULT,
            flight_number=flight_number,
            flight_id=flight.id,
            status=status,
            status_kind=kind,
        )

    def build_board(
        self,
        airport_code: str,
        date_str: str,
        mode: str,
        now: datetime | None = None,
    ) -> list[BoardRow]:
        """Build a sorted arrivals/departures board for one airport and date.

        Raises ``ValueError`` if ``date_str`` is not a valid YYYY-MM-DD date.
        """
        if mode not in _VALID_MODES:
            mode = ARRIVALS
        airport_code = airport_code.upper()
        now = now or datetime.now()

        airport_service = AirportService(self._session)
        flight_service = FlightService(self._session)

        # Stable subset of routes for this board.
        seed = _hash(f"{airport_code}-{date_str}-{mode}") % (2**32)
        others = [
            a.code for a in airport_service.list_airports() if a.code != airport_code
        ]
        picked = Random(seed).sample(others, min(ROUTES_PER_BOARD, len(others)))

        rows: list[BoardRow] = []
        for other_code in picked:
            # Arrivals: other -> board airport. Departures: board airport -> other.
            if mode == ARRIVALS:
                origin, destination = other_code, airport_code
            else:
                origin, destination = airport_code, other_code
            flights = flight_service.generate_flights(origin, destination, date_str)
            rows.extend(
                self._make_row(flight, mode, now)
                for flight in flights[:FLIGHTS_PER_ROUTE]
            )

        rows.sort(key=lambda row: row.scheduled)
        return rows


def get_board_service(
    session: Annotated[Session, Depends(get_session)],
) -> BoardService:
    """FastAPI dependency: a board service bound to the request session."""
    return BoardService(session)
