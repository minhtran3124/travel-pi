"""FeedbackRepository: fold rules, idempotent replay, race recovery (SC-3).

Fold cases follow specs/user-feedback-v1 DESIGN §3.3, ordered by
``(created_at, id)``. Rows for the fold tests are inserted directly with explicit
``created_at`` / ``id`` so the order under test is deterministic.
"""

import pytest
from app.db import models
from app.db.base import Base
from app.db.engine import get_session_factory
from app.enums import FeedbackAction, FeedbackReasonCode
from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import EffectiveFeedback

MSG = "msg-1"


@pytest.fixture
def factory(tmp_path):
    factory = get_session_factory(f"sqlite:///{tmp_path / 'feedback.db'}")
    Base.metadata.create_all(bind=factory().get_bind())
    return factory


@pytest.fixture
def repo(factory):
    return FeedbackRepository(factory)


def _insert(factory, *, id, created_at, action, **cols):
    defaults = {
        "user_id": "u1",
        "conversation_id": "c1",
        "assistant_message_id": MSG,
        "agent_run_id": "run-1",
        "source": "chat_message_actions",
        "client_event_id": f"ce-{id}",
        "request_fingerprint": f"fp-{id}",
    }
    with factory() as s:
        s.add(
            models.FeedbackEvent(
                id=id,
                created_at=created_at,
                action=action.value,
                **{**defaults, **cols},
            )
        )
        s.commit()


def _count(factory) -> int:
    with factory() as s:
        return s.query(models.FeedbackEvent).count()


# --- fold -------------------------------------------------------------------


def test_effective_for_unknown_message_is_none(repo):
    assert repo.effective_for(["nope"]) == {"nope": None}
    assert repo.effective_for([]) == {}


def test_set_rating_folds_to_effective(factory, repo):
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=1,
    )
    assert repo.effective_for([MSG]) == {
        MSG: EffectiveFeedback(
            rating="helpful",
            reason_code=None,
            comment_present=False,
            rating_event_id="e1",
            updated_at="2026-01-01T00:00:01",
        )
    }


def test_replace_rating_clears_old_negative_detail(factory, repo):
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=-1,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:02",
        action=FeedbackAction.ADD_DETAIL,
        reason_code="incorrect",
        comment="x",
    )
    _insert(
        factory,
        id="e3",
        created_at="2026-01-01T00:00:03",
        action=FeedbackAction.SET_RATING,
        rating=1,
        supersedes_event_id="e1",
    )
    eff = repo.effective_for([MSG])[MSG]
    assert eff.rating == "helpful"
    assert eff.rating_event_id == "e3"
    assert eff.reason_code is None
    assert eff.comment_present is False
    assert eff.updated_at == "2026-01-01T00:00:03"


def test_add_detail_enriches_negative_rating(factory, repo):
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=-1,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:02",
        action=FeedbackAction.ADD_DETAIL,
        reason_code="incorrect",
    )
    _insert(
        factory,
        id="e3",
        created_at="2026-01-01T00:00:03",
        action=FeedbackAction.ADD_DETAIL,
        comment="closed on Tuesdays",
    )
    eff = repo.effective_for([MSG])[MSG]
    assert eff.rating == "not_helpful"
    assert eff.rating_event_id == "e1"
    assert eff.reason_code == "incorrect"  # kept when a later detail has none
    assert eff.reason_code is FeedbackReasonCode.INCORRECT  # enum, not raw str
    assert eff.comment_present is True
    assert eff.updated_at == "2026-01-01T00:00:03"


def test_add_detail_with_retired_reason_code_folds_to_other(factory, repo):
    """A code no longer in the enum (append-only log) must not crash the fold."""
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=-1,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:02",
        action=FeedbackAction.ADD_DETAIL,
        reason_code="retired_code",
    )
    eff = repo.effective_for([MSG])[MSG]
    assert eff.reason_code is FeedbackReasonCode.OTHER


def test_add_detail_on_positive_rating_is_ignored(factory, repo):
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=1,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:02",
        action=FeedbackAction.ADD_DETAIL,
        reason_code="incorrect",
    )
    eff = repo.effective_for([MSG])[MSG]
    assert eff.rating == "helpful"
    assert eff.reason_code is None
    assert eff.updated_at == "2026-01-01T00:00:01"


def test_retract_clears_rating_and_detail(factory, repo):
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=-1,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:02",
        action=FeedbackAction.ADD_DETAIL,
        reason_code="incorrect",
    )
    _insert(
        factory,
        id="e3",
        created_at="2026-01-01T00:00:03",
        action=FeedbackAction.RETRACT_RATING,
    )
    assert repo.effective_for([MSG]) == {MSG: None}


def test_stale_retract_and_detail_are_no_ops(factory, repo):
    # A retract with nothing active, then a detail with nothing active.
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.RETRACT_RATING,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:02",
        action=FeedbackAction.ADD_DETAIL,
        comment="late",
    )
    assert repo.effective_for([MSG]) == {MSG: None}
    # And a set after them is unaffected by the stale rows.
    _insert(
        factory,
        id="e3",
        created_at="2026-01-01T00:00:03",
        action=FeedbackAction.SET_RATING,
        rating=1,
    )
    assert repo.effective_for([MSG])[MSG].rating_event_id == "e3"


def test_fold_breaks_created_at_ties_by_id(factory, repo):
    _insert(
        factory,
        id="b",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=1,
    )
    _insert(
        factory,
        id="a",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=-1,
    )
    assert repo.effective_for([MSG])[MSG].rating_event_id == "b"


def test_effective_for_many_messages_in_one_call(factory, repo):
    _insert(
        factory,
        id="e1",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=1,
    )
    _insert(
        factory,
        id="e2",
        created_at="2026-01-01T00:00:01",
        action=FeedbackAction.SET_RATING,
        rating=-1,
        assistant_message_id="msg-2",
    )
    out = repo.effective_for([MSG, "msg-2", "msg-3"])
    assert out[MSG].rating == "helpful"
    assert out["msg-2"].rating == "not_helpful"
    assert out["msg-3"] is None


# --- append / idempotency ---------------------------------------------------


def _append(repo, **overrides):
    kwargs = {
        "user_id": "u1",
        "conversation_id": "c1",
        "assistant_message_id": MSG,
        "agent_run_id": "run-1",
        "action": FeedbackAction.SET_RATING,
        "rating": 1,
        "client_event_id": "ce-1",
        "request_fingerprint": "fp-1",
        "source": "chat_message_actions",
    }
    return repo.append(**{**kwargs, **overrides})


def test_append_returns_row_and_find_by_client_event(repo):
    assert repo.find_by_client_event(user_id="u1", client_event_id="ce-1") is None
    rec, inserted = _append(repo, locale="en")
    assert inserted is True
    assert rec.id and rec.created_at
    assert rec.action is FeedbackAction.SET_RATING
    assert rec.rating == 1
    assert rec.locale == "en"
    found = repo.find_by_client_event(user_id="u1", client_event_id="ce-1")
    assert found == rec
    # The key is scoped per actor.
    assert repo.find_by_client_event(user_id="u2", client_event_id="ce-1") is None


def test_replay_same_key_appends_nothing_and_returns_winner(factory, repo):
    first, _ = _append(repo)
    again, inserted = _append(repo, request_fingerprint="fp-different")
    assert inserted is False  # the caller can tell a race loss from an insert
    assert again.id == first.id
    assert again.request_fingerprint == "fp-1"  # the winner, so the service can compare
    assert _count(factory) == 1


def test_race_recovery_keeps_shared_session_usable(factory, repo):
    """Live-session mode: the savepoint rollback leaves the UoW session usable."""
    _append(repo)
    with factory() as s:
        live = FeedbackRepository(s)
        winner, inserted = live.append(
            user_id="u1",
            conversation_id="c1",
            assistant_message_id=MSG,
            agent_run_id="run-1",
            action=FeedbackAction.SET_RATING,
            rating=-1,
            client_event_id="ce-1",
            request_fingerprint="fp-2",
            source="chat_message_actions",
        )
        assert winner.rating == 1
        assert inserted is False
        # Session still works after the recovered IntegrityError.
        second, inserted = live.append(
            user_id="u1",
            conversation_id="c1",
            assistant_message_id=MSG,
            agent_run_id="run-1",
            action=FeedbackAction.RETRACT_RATING,
            client_event_id="ce-2",
            request_fingerprint="fp-3",
            source="chat_message_actions",
        )
        s.commit()
    assert inserted is True
    assert second.action is FeedbackAction.RETRACT_RATING
    assert _count(factory) == 2
    assert repo.effective_for([MSG]) == {MSG: None}


def test_same_key_different_user_is_a_separate_event(factory, repo):
    _append(repo)
    other, inserted = _append(repo, user_id="u2")
    assert inserted is True
    assert other.user_id == "u2"
    assert _count(factory) == 2
