"""Owner-scoping of the agent's saved-place read (review-A security hardening, SC-8).

`resolve_place(source="saved")` used to reach `SavedPlaceRepository.get(place_id)`
with no owner, so an LLM-invoked tool with a user-controlled `place_id` / `SPL-`
short code could read ANY user's saved place (name, address, coords, notes = PII);
the short-code branch scanned every user's rows. The agent runs under the
authenticated JWT sub (wave 1), so the owner is now injected from graph state
(`TravelAgentState.user_id`) and threaded through
`PlaceService.resolve` → `SavedPlaceRepository.get(place_id, user_id=...)`.

These tests pin the cross-user boundary at BOTH the tool seam (real InjectedState
injection through a `ToolNode`) and the service/repo seam, for id AND SPL- code,
and confirm the public `catalog` source is unchanged.
"""

from typing import Annotated, TypedDict

import pytest
from app.db.engine import get_session_factory
from app.repositories.saved_place import SavedPlaceRepository
from app.schemas.saved_place import SavedPlace
from app.services.place_service import PlaceService
from app.tools.place_tools import resolve_place
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

USER_A = "owner-a"
USER_B = "owner-b"


class _State(TypedDict):
    """Minimal graph state carrying the injected owner (mirrors TravelAgentState)."""

    messages: Annotated[list, add_messages]
    user_id: str


def _tool_graph():
    """Compile a one-node graph running resolve_place through a real ToolNode.

    ToolNode performs ``InjectedState`` injection only inside a Pregel runtime,
    so we drive it via a compiled graph — the same path the agent uses.
    """
    g = StateGraph(_State)
    g.add_node("tools", ToolNode([resolve_place]))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    return g.compile()


def _make_sp(id_: str, name: str) -> SavedPlace:
    return SavedPlace(
        id=id_,
        created_at="2026-06-18T00:00:00+00:00",
        name=name,
        city="Hanoi",
        address="12 Secret Lane",
        notes="private note",
    )


@pytest.fixture
def saved_places(agent_db):
    """Seed one saved place per user on the agent DB; return (a_place, b_place)."""
    factory = get_session_factory(agent_db)
    repo = SavedPlaceRepository(factory)
    a = repo.add(_make_sp("a-uuid-1", "A's Hideaway"), USER_A)
    b = repo.add(_make_sp("b-uuid-1", "B's Cafe"), USER_B)
    return a, b


def _resolve_via_tool(place_id: str, user_id: str) -> object:
    """Invoke resolve_place(source="saved") through a ToolNode as ``user_id``.

    Routes injection through the real ``ToolNode`` (not a direct ``.func`` call),
    so ``user_id`` is supplied ONLY by graph state — exactly the agent's path.
    Returns the tool's decoded value (a dict, or None).
    """
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-1",
                "name": "resolve_place",
                "args": {"place_id": place_id, "source": "saved"},
            }
        ],
    )
    out = _tool_graph().invoke({"messages": [ai], "user_id": user_id})
    tool_msg = out["messages"][-1]
    # ToolNode JSON-encodes non-string content; None round-trips to the "null"
    # string. Assert on the raw string content so both are handled uniformly.
    return tool_msg.content


# --------------------------------------------------------------------------- #
# Tool seam — real InjectedState injection through ToolNode
# --------------------------------------------------------------------------- #


def test_agent_cannot_read_other_users_saved_place_by_id(saved_places):
    a, _ = saved_places
    content = _resolve_via_tool(a.id, USER_B)
    assert a.name not in content  # B's agent sees a miss, not A's PII
    assert "Secret Lane" not in content


def test_agent_cannot_read_other_users_saved_place_by_short_code(saved_places):
    a, _ = saved_places
    content = _resolve_via_tool(a.short_code, USER_B)
    assert a.name not in content  # short-code scan is owner-filtered too
    assert "Secret Lane" not in content


def test_agent_can_read_own_saved_place_by_id(saved_places):
    a, _ = saved_places
    content = _resolve_via_tool(a.id, USER_A)
    assert a.name in content


def test_agent_can_read_own_saved_place_by_short_code(saved_places):
    a, _ = saved_places
    content = _resolve_via_tool(a.short_code, USER_A)
    assert a.name in content


def test_resolve_place_hides_injected_user_id_from_model():
    """`user_id` is injected — it must not appear in the model-facing schema."""
    assert "user_id" not in resolve_place.args
    assert "place_id" in resolve_place.args
    assert "source" in resolve_place.args


# --------------------------------------------------------------------------- #
# Service / repo seam — deterministic owner scoping (id + SPL- code)
# --------------------------------------------------------------------------- #


def test_service_resolve_saved_owner_isolation(agent_db, saved_places):
    a, _ = saved_places
    with get_session_factory(agent_db)() as s:
        svc = PlaceService(s)
        # Owner resolves their own place by id and by short code.
        assert svc.resolve(a.id, "saved", user_id=USER_A).name == a.name
        assert svc.resolve(a.short_code, "saved", user_id=USER_A).id == a.id
        # A different user gets a miss (None) for both id and short code.
        assert svc.resolve(a.id, "saved", user_id=USER_B) is None
        assert svc.resolve(a.short_code, "saved", user_id=USER_B) is None


def test_repo_get_owner_filters_short_code(agent_db, saved_places):
    a, _ = saved_places
    repo = SavedPlaceRepository(get_session_factory(agent_db))
    assert repo.get(a.short_code, user_id=USER_A).id == a.id
    assert repo.get(a.short_code, user_id=USER_B) is None
    assert repo.get(a.id, user_id=USER_B) is None


def test_catalog_resolve_unchanged(agent_db, saved_places):
    """The public `catalog` source ignores user_id and still resolves for anyone."""
    with get_session_factory(agent_db)() as s:
        svc = PlaceService(s)
        seeded = svc.list_places()
        assert seeded, "catalog seed missing"
        target = seeded[0]
        # Same result whoever asks; user_id is irrelevant to the public catalog.
        assert svc.resolve(target.id, "catalog", user_id=USER_B).id == target.id
        assert svc.resolve(target.id, "catalog").id == target.id
