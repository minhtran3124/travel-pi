"""Grader-only proposal validator for the trip-research deep agent.

`validate_proposal` reads `/plan/proposal.json` through the run's backend and checks every
id it carries — place, flight-offer and hotel — against the database. It is bound only to
the research grader (`RubricMiddleware`), never registered in `tools/registry.py`, so
`/agent/manifest` and the MCP surface stay byte-identical (non-replacement guarantee).
"""

from __future__ import annotations

import json
from typing import Any

from deepagents.backends.protocol import BackendProtocol
from langchain_core.tools import BaseTool, tool

from app.repositories.flight import FlightIndexRepository
from app.repositories.hotel_ref import HotelRepository
from app.repositories.place_ref import PlaceRepository
from app.tools._base import session_scope

PROPOSAL_PATH = "/plan/proposal.json"


def _proposal_ids(
    proposal: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Collect ``(place_ids, offer_ids, hotel_ids)`` from a proposal document."""
    place_ids = [
        entry["place_id"]
        for entry in proposal.get("itinerary", [])
        if isinstance(entry, dict) and entry.get("place_id")
    ]
    place_ids += [pid for pid in proposal.get("shortlist", []) if pid]
    offer_ids = [oid for oid in proposal.get("flights", []) if oid]
    hotel_ids = [hid for hid in proposal.get("hotels", []) if hid]
    return place_ids, offer_ids, hotel_ids


def _unknown_ids(
    place_ids: list[str],
    offer_ids: list[str],
    hotel_ids: list[str],
) -> list[str]:
    """Return every id that does not resolve to a real row, in place/offer/hotel order."""
    with session_scope() as s:
        known_places = PlaceRepository(s).known_ids(place_ids)
        known_offers = FlightIndexRepository(s).known_ids(offer_ids)
        known_hotels = HotelRepository(s).known_ids(hotel_ids)
    unknown = [pid for pid in place_ids if pid not in known_places]
    unknown += [oid for oid in offer_ids if oid not in known_offers]
    unknown += [hid for hid in hotel_ids if hid not in known_hotels]
    return unknown


def make_validate_proposal(backend: BackendProtocol) -> BaseTool:
    """Build the grader-only ``validate_proposal`` tool bound to *backend*."""

    @tool
    def validate_proposal() -> dict[str, Any]:
        """Check every id in `/plan/proposal.json` against the database.

        Returns `{"valid": bool, "unknown_ids": [...]}`; `valid` is true only when every
        place, flight-offer and hotel id in the proposal resolves to a real row.
        """
        response = backend.download_files([PROPOSAL_PATH])[0]
        if response.error is not None or response.content is None:
            return {"valid": False, "unknown_ids": []}
        try:
            proposal = json.loads(response.content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {"valid": False, "unknown_ids": []}
        if not isinstance(proposal, dict):
            return {"valid": False, "unknown_ids": []}
        unknown = _unknown_ids(*_proposal_ids(proposal))
        return {"valid": not unknown, "unknown_ids": unknown}

    return validate_proposal
