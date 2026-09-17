"""Airport lookup over the DB-backed airport repository."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.airport import AirportRepository
from app.schemas.airport import Airport


class AirportService:
    """Airport lookup over the DB-backed airport repository."""

    def __init__(self, session: Session) -> None:
        self._airport = AirportRepository(session)

    def list_airports(self) -> list[Airport]:
        """Return the supported airports."""
        return self._airport.list()

    def get_airport(self, code: str) -> Airport | None:
        """Return the airport for an IATA ``code``, or ``None`` if unknown.

        Flights can be generated for any code, so callers must handle ``None``.
        """
        return self._airport.get(code)


def get_airport_service(
    session: Annotated[Session, Depends(get_session)],
) -> AirportService:
    """FastAPI dependency: an airport service bound to the request session."""
    return AirportService(session)
