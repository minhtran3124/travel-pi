"""BotHeartbeatRepository: upsert idempotency, live window, prune, delete."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import BotHeartbeat
from app.repositories.bot_heartbeat import BotHeartbeatRepository


@pytest.fixture
def factory(tmp_db):
    f = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with f() as s:
        s.query(BotHeartbeat).delete()
        s.commit()
    return f


@pytest.fixture
def repo(factory):
    return BotHeartbeatRepository(factory)


def _beat(
    repo, instance="api-1", pid=1, last_seen="2026-10-29T10:00:00.000+00:00", **kw
):
    repo.upsert(
        instance_id=instance,
        pid=pid,
        role=kw.pop("role", "web"),
        host="h",
        started_at="2026-10-29T09:00:00.000+00:00",
        last_seen=last_seen,
        **kw,
    )


def test_upsert_twice_is_one_row_and_moves_last_seen(repo):
    _beat(repo, snapshot={"turns": []})
    _beat(repo, last_seen="2026-10-29T10:00:03.000+00:00", snapshot={"turns": [1]})
    rows = repo.list_live("2026-10-29T00:00:00.000+00:00")
    assert len(rows) == 1
    assert rows[0].last_seen == "2026-10-29T10:00:03.000+00:00"
    assert rows[0].snapshot == {"turns": [1]}


def test_two_processes_in_one_instance_are_two_rows(repo):
    _beat(repo, pid=1)
    _beat(repo, pid=2)
    assert [(r.instance_id, r.pid) for r in repo.list_live("")] == [
        ("api-1", 1),
        ("api-1", 2),
    ]


def test_snapshot_defaults_to_empty_dict(repo):
    _beat(repo)
    assert repo.list_live("")[0].snapshot == {}


def test_list_live_window(repo):
    _beat(repo, pid=1, last_seen="2026-10-29T10:00:00.000+00:00")
    _beat(repo, pid=2, last_seen="2026-10-29T10:00:10.000+00:00")
    live = repo.list_live("2026-10-29T10:00:05.000+00:00")
    assert [r.pid for r in live] == [2]


def test_prune_removes_only_older_rows(repo):
    _beat(repo, pid=1, last_seen="2026-10-29T08:00:00.000+00:00")
    _beat(repo, pid=2, last_seen="2026-10-29T10:00:00.000+00:00")
    assert repo.prune("2026-10-29T09:00:00.000+00:00") == 1
    assert [r.pid for r in repo.list_live("")] == [2]


def test_delete_removes_one_process(repo):
    _beat(repo, pid=1)
    _beat(repo, pid=2)
    repo.delete("api-1", 1)
    assert [r.pid for r in repo.list_live("")] == [2]
