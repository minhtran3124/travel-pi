"""Anonymous claim moves conversations, agent_runs and feedback_events together (SC-4)."""

import pytest
from app.db import models
from app.db.base import Base
from app.db.engine import get_session_factory
from app.enums import FeedbackAction
from app.repositories.agent_run import AgentRunRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.feedback import FeedbackRepository

ANON = "anon-1"
OWNER = "user-1"


@pytest.fixture
def factory(tmp_path):
    factory = get_session_factory(f"sqlite:///{tmp_path / 'claim.db'}")
    Base.metadata.create_all(bind=factory().get_bind())
    return factory


def _start_run(factory, run_id, *, user_id, conversation_id):
    AgentRunRepository(factory).start(
        run_id,
        user_id=user_id,
        conversation_id=conversation_id,
        thread_id="t",
        trip_id=None,
        channel="chat",
        kind="turn",
        started_at="2026-01-01T00:00:00",
    )


def _owners(factory, model) -> dict[str, str]:
    with factory() as s:
        return {row.id: row.user_id for row in s.query(model).all()}


def test_reassign_moves_all_three_tables_and_leaves_other_users_alone(factory):
    conv = ConversationRepository(factory)
    c1 = conv.create_conversation(user_id=ANON)
    c2 = conv.create_conversation(user_id="someone-else")
    _start_run(factory, "run-1", user_id=ANON, conversation_id=c1.id)
    _start_run(factory, "run-2", user_id="someone-else", conversation_id=c2.id)
    msg = conv.append_message(
        conversation_id=c1.id, role="assistant", content="hi", agent_run_id="run-1"
    )
    fb = FeedbackRepository(factory)
    ev, _ = fb.append(
        user_id=ANON,
        conversation_id=c1.id,
        assistant_message_id=msg.id,
        agent_run_id="run-1",
        action=FeedbackAction.SET_RATING,
        rating=1,
        client_event_id="ce-1",
        request_fingerprint="fp",
        source="chat_message_actions",
    )

    assert conv.reassign_user(from_user_id=ANON, to_user_id=OWNER) == 1

    assert _owners(factory, models.Conversation) == {
        c1.id: OWNER,
        c2.id: "someone-else",
    }
    assert _owners(factory, models.AgentRun) == {
        "run-1": OWNER,
        "run-2": "someone-else",
    }
    assert _owners(factory, models.FeedbackEvent) == {ev.id: OWNER}
    # The moved feedback is now found under the new owner's key, not the old one.
    assert fb.find_by_client_event(user_id=OWNER, client_event_id="ce-1") is not None
    assert fb.find_by_client_event(user_id=ANON, client_event_id="ce-1") is None


def test_reassign_without_feedback_still_moves_runs(factory):
    conv = ConversationRepository(factory)
    c1 = conv.create_conversation(user_id=ANON)
    _start_run(factory, "run-1", user_id=ANON, conversation_id=c1.id)

    assert conv.reassign_user(from_user_id=ANON, to_user_id=OWNER) == 1

    assert _owners(factory, models.AgentRun) == {"run-1": OWNER}
    assert _owners(factory, models.FeedbackEvent) == {}


def test_reassign_nothing_returns_zero(factory):
    conv = ConversationRepository(factory)
    assert conv.reassign_user(from_user_id="ghost", to_user_id=OWNER) == 0


def test_get_message_for_feedback_joins_owner_and_run_status(factory):
    conv = ConversationRepository(factory)
    c1 = conv.create_conversation(user_id=OWNER)
    _start_run(factory, "run-1", user_id=OWNER, conversation_id=c1.id)
    AgentRunRepository(factory).finish(
        "run-1",
        status="completed",
        current_flow=None,
        finished_at="2026-01-01T00:00:01",
        metrics={},
    )
    linked = conv.append_message(
        conversation_id=c1.id,
        role="assistant",
        content="a",
        message_id="explicit-id",
        agent_run_id="run-1",
    )
    assert linked.id == "explicit-id"
    unlinked = conv.append_message(conversation_id=c1.id, role="user", content="u")
    dangling = conv.append_message(
        conversation_id=c1.id, role="assistant", content="b", agent_run_id="run-missing"
    )

    view = conv.get_message_for_feedback("explicit-id")
    assert view.owner_user_id == OWNER
    assert view.conversation_id == c1.id
    assert view.role == "assistant"
    assert view.agent_run_id == "run-1"
    assert view.run_status == "completed"

    assert conv.get_message_for_feedback(unlinked.id).run_status is None
    assert conv.get_message_for_feedback(unlinked.id).agent_run_id is None
    assert conv.get_message_for_feedback(dangling.id).run_status is None
    assert conv.get_message_for_feedback("nope") is None
