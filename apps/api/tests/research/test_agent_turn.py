"""SC-7: a scripted full turn drives the whole loop to a satisfied rubric.

todos -> task(flights) writes a dimension file -> the main agent writes ``/research/overview.md``
and ``/plan/proposal.json`` -> the grader calls ``validate_proposal`` (which finds one unknown
place id against a real seeded DB) and asks for a revision -> the agent edits the proposal to a
real id -> the second grade is ``satisfied``. ``aget_state`` shows ``_rubric_status == "satisfied"``.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.place import Place
from app.db.seed import seed_all
from deepagents.middleware.rubric import GraderResponse
from sqlalchemy import select

from tests.research.conftest import THREAD_CONFIG, build, context, rubric

_BOGUS_PLACE = "BOGUS-PLACE-XYZ"


@pytest.fixture
def real_place_id(tmp_path, monkeypatch) -> str:
    """Seed a temp DB and point ``session_scope`` at it; return one real place id."""
    url = f"sqlite:///{tmp_path / 'research.db'}"
    Base.metadata.create_all(get_engine(url))
    seed_all(get_session_factory(url))

    # session_scope() reads only .database_url; point it at the seeded temp DB.
    import app.tools._base as base

    monkeypatch.setattr(
        base, "get_settings", lambda: type("S", (), {"database_url": url})()
    )
    with get_session_factory(url)() as session:
        return session.scalars(select(Place.id)).first()


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": call_id}]}


def _proposal(place_id: str) -> str:
    return json.dumps(
        {
            "itinerary": [
                {"day": 1, "time": "09:00", "place_id": place_id, "title": "Morning"}
            ],
            "shortlist": [],
            "flights": [],
            "hotels": [],
            "budget_estimate": 0,
        }
    )


def _grader_response(result: str, passed: bool) -> dict:
    criterion = {"name": "Proposal ids resolve", "passed": passed}
    if not passed:
        criterion["gap"] = "validate_proposal reported one unknown place id"
    return {
        "content": "",
        "tool_calls": [
            {
                "name": GraderResponse.__name__,
                "args": {
                    "result": result,
                    "explanation": f"proposal {result}",
                    "criteria": [criterion],
                },
                "id": f"grade-{result}",
            }
        ],
    }


def test_full_turn_reaches_satisfied(store, real_place_id) -> None:
    # Main model (shared with the flights subagent, in call order).
    model = FakeLLM(
        responses=[
            _tool_call(
                "write_todos",
                {"todos": [{"content": "research the trip", "status": "in_progress"}]},
                "todos",
            ),
            _tool_call(
                "task",
                {"description": "research flights", "subagent_type": "flights"},
                "task",
            ),
            # --- flights subagent consumes here (shared cursor) ---
            _tool_call(
                "write_file",
                {
                    "file_path": "/research/flights.md",
                    "content": "DAD -> BKK offer FL1 (search_flights)",
                },
                "sub-write",
            ),
            {"content": "flights researched"},
            # --- back to the main agent ---
            _tool_call(
                "write_file",
                {
                    "file_path": "/research/overview.md",
                    "content": "Trip overview (get_trip_summary)",
                },
                "overview",
            ),
            _tool_call(
                "write_file",
                {
                    "file_path": "/plan/proposal.json",
                    "content": _proposal(_BOGUS_PLACE),
                },
                "proposal",
            ),
            {"content": "dossier ready for review"},
            # --- after the first grade asks for a revision ---
            _tool_call(
                "edit_file",
                {
                    "file_path": "/plan/proposal.json",
                    "old_string": _BOGUS_PLACE,
                    "new_string": real_place_id,
                },
                "fix",
            ),
            {"content": "proposal corrected"},
        ]
    )
    grader = FakeLLM(
        responses=[
            _tool_call("validate_proposal", {}, "vp-1"),
            _grader_response("needs_revision", passed=False),
            _tool_call("validate_proposal", {}, "vp-2"),
            _grader_response("satisfied", passed=True),
        ]
    )
    agent = build(store, llm=model, grader=grader)

    agent.invoke(
        {
            "messages": [{"role": "user", "content": "research my trip in depth"}],
            "rubric": rubric(),
        },
        THREAD_CONFIG,
        context=context(),
    )

    snapshot = asyncio.run(agent.aget_state(THREAD_CONFIG))
    assert snapshot.values["_rubric_status"] == "satisfied"

    # The dossier and the corrected proposal landed in the store.
    ns = ("users", "u1", "research", "t1")
    keys = {i.key for i in store.search(ns)}
    assert {"/flights.md", "/overview.md", "/proposal.json"} <= keys
    proposal = json.loads(store.get(ns, "/proposal.json").value["content"])
    assert proposal["itinerary"][0]["place_id"] == real_place_id
