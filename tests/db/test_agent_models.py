"""Agent persistence models + repository (specs/travel-agent Task 1.3)."""

import pytest
from app.db.engine import get_session_factory
from app.enums import JobStatus
from app.repositories.conversation import ConversationRepository


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'agent.db'}"
    factory = get_session_factory(url)
    # create_all via Base metadata on this engine
    from app.db.base import Base

    Base.metadata.create_all(bind=factory().get_bind())
    return ConversationRepository(factory)


def test_create_and_get_conversation(repo):
    conv = repo.create_conversation(user_id="u1", trip_id="t1", title="Tokyo")
    assert conv.id
    assert conv.created_at
    fetched = repo.get(conv.id)
    assert fetched.user_id == "u1"
    assert fetched.trip_id == "t1"


def test_list_for_user(repo):
    repo.create_conversation(user_id="u1", title="a")
    repo.create_conversation(user_id="u1", title="b")
    repo.create_conversation(user_id="u2", title="c")
    assert len(repo.list_for_user("u1")) == 2
    assert len(repo.list_for_user("u2")) == 1


def test_append_and_list_messages(repo):
    conv = repo.create_conversation(user_id="u1")
    repo.append_message(conversation_id=conv.id, role="user", content="hi")
    repo.append_message(
        conversation_id=conv.id,
        role="assistant",
        content="",
        tool_calls=[{"name": "search_places", "args": {"city": "Tokyo"}}],
    )
    msgs = repo.list_messages(conv.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].tool_calls[0]["name"] == "search_places"


def test_job_lifecycle(repo):
    job = repo.create_job(kind="agent_run")
    assert job.status == JobStatus.PENDING
    running = repo.set_job_status(job.id, status=JobStatus.RUNNING)
    assert running.status == JobStatus.RUNNING
    done = repo.set_job_status(
        job.id, status=JobStatus.SUCCEEDED, result={"answer": "ok"}
    )
    assert done.status == JobStatus.SUCCEEDED
    assert done.result == {"answer": "ok"}


def test_set_job_status_missing_returns_none(repo):
    assert repo.set_job_status("nope", status=JobStatus.FAILED) is None
