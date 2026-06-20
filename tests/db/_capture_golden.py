"""One-shot helper that captured the pre-migration golden determinism fixtures.

Run ON THE CLEAN TREE (Task A0) to dump the verbatim JSON response bodies for
the deterministic generation endpoints into ``tests/db/fixtures/``. These are
the pre-migration oracle for Chunk F's byte-equality assertion — do NOT
regenerate them after any migration code change.

Working URLs captured (recorded here because the plan's example URLs were
adjusted to the real route signatures):
  - GET /flights/search?origin=SGN&destination=HAN&departure_date=2026-09-01
  - GET /hotels/availability?city=Da%20Nang&check_in=2026-09-01&check_out=2026-09-04
    (the live route is ``/hotels/availability`` taking a ``city`` query param,
    not ``/hotels/{id}/availability``; the plan's hotel-id URL does not exist.)

Usage:
    .venv/bin/python -m tests.db._capture_golden
"""

import json
import os
import tempfile
from pathlib import Path

from app.db.engine import get_session_factory
from app.main import create_app
from app.repositories.flight import FlightIndexRepository
from app.services import flight_service
from app.services.booking_service import BookingService
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"

FLIGHTS_URL = "/flights/search?origin=SGN&destination=HAN&departure_date=2026-09-01"
AVAIL_URL = "/hotels/availability?city=Da+Nang&check_in=2026-09-01&check_out=2026-09-04"


def _client(tmp_db: str) -> TestClient:
    # Mirror tests/conftest.py: isolate persisted flight ids in a temp DB so
    # capture does not depend on the dev travel.db. Deterministic generation is
    # driven only by app/data + the MD5 seed, so the engine choice is irrelevant
    # to the response bodies.
    svc = BookingService(tmp_db)
    svc.init_db()
    flight_service.set_index_repo(FlightIndexRepository(get_session_factory(tmp_db)))
    return TestClient(create_app())


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp_db = f"sqlite:///{os.path.join(d, 'capture.db')}"
        with _client(tmp_db) as c:
            flights = c.get(FLIGHTS_URL)
            avail = c.get(AVAIL_URL)
            assert flights.status_code == 200, (flights.status_code, flights.text)
            assert avail.status_code == 200, (avail.status_code, avail.text)
            (FIXTURES / "golden_flights.json").write_text(
                json.dumps(flights.json(), indent=2, ensure_ascii=False) + "\n"
            )
            (FIXTURES / "golden_hotel_availability.json").write_text(
                json.dumps(avail.json(), indent=2, ensure_ascii=False) + "\n"
            )
            print("flights results:", len(flights.json().get("results", [])))
            print("availability total:", avail.json().get("total"))


if __name__ == "__main__":
    main()
