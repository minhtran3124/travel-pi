"""BotsService aggregation and GET /dashboard/bots.json (fixture-built heartbeat rows)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import BotHeartbeat
from app.db.session import get_session
from app.main import create_app
from app.repositories.bot_heartbeat import BotHeartbeatRepository
from app.services.bots_service import BotsService
from fastapi.testclient import TestClient

NOW = datetime(2026, 10, 29, 10, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


@pytest.fixture
def factory(tmp_db):
    f = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with f() as s:
        s.query(BotHeartbeat).delete()
        s.commit()
    yield f
    with f() as s:
        s.query(BotHeartbeat).delete()
        s.commit()


def _beat(factory, instance="api-1", pid=1, age=1, role="web", up=3600, snapshot=None):
    BotHeartbeatRepository(factory).upsert(
        instance_id=instance,
        pid=pid,
        role=role,
        host="h",
        started_at=_iso(NOW - timedelta(seconds=up)),
        last_seen=_iso(NOW - timedelta(seconds=age)),
        snapshot=snapshot,
    )


def _turn(conv, *agents, kind="chat"):
    return {
        "conv": conv,
        "kind": kind,
        "agents": [
            {
                "agent": a,
                "phase": "tools",
                "tool": "search",
                "since": _iso(NOW - timedelta(seconds=7)),
            }
            for a in agents
        ],
    }


def _aggregate(factory):
    with factory() as s:
        return BotsService(s).aggregate(NOW)


def test_empty(factory):
    out = _aggregate(factory)
    assert out["bots"] == []
    assert out["counts"] == {"online": 0, "busy": 0, "agents": 0, "turns": 0}


def test_two_processes_of_one_instance_merge(factory):
    _beat(
        factory, pid=1, up=100, snapshot={"turns": [_turn("c1", "planner", "budget")]}
    )
    _beat(factory, pid=2, up=500, snapshot={"turns": [_turn("c2", "journal")]})
    out = _aggregate(factory)
    assert len(out["bots"]) == 1
    bot = out["bots"][0]
    assert bot["id"] == "api-1" and bot["processes"] == 2
    assert bot["uptime_s"] == 500
    assert [t["conv"] for t in bot["turns"]] == ["c1", "c2"]
    assert bot["agent_count"] == 3
    assert bot["turns"][0]["agents"][0] == {
        "agent": "planner",
        "phase": "tools",
        "tool": "search",
        "elapsed_s": 7,
    }
    assert out["counts"] == {"online": 1, "busy": 1, "agents": 3, "turns": 2}


@pytest.mark.parametrize(
    "age,status",
    [(0, "online"), (9, "online"), (11, "stale"), (59, "stale")],
)
def test_status_windows(factory, age, status):
    _beat(factory, age=age, snapshot={"turns": [_turn("c1", "planner")]})
    bot = _aggregate(factory)["bots"][0]
    assert bot["status"] == status
    if status == "stale":
        assert bot["turns"] == [] and bot["agent_count"] == 0


def test_older_than_sixty_seconds_dropped(factory):
    _beat(factory, age=61)
    assert _aggregate(factory)["bots"] == []


def test_instance_online_when_any_process_fresh(factory):
    _beat(factory, pid=1, age=30, snapshot={"turns": [_turn("old", "planner")]})
    _beat(factory, pid=2, age=2, snapshot={"turns": [_turn("new", "budget")]})
    bot = _aggregate(factory)["bots"][0]
    assert bot["status"] == "online" and bot["processes"] == 2
    assert [t["conv"] for t in bot["turns"]] == ["new"]


def test_role_mapping_and_ordering(factory):
    _beat(factory, instance="worker", role="worker")
    _beat(factory, instance="api-2", role="web")
    _beat(factory, instance="api-1", role="bogus")
    bots = _aggregate(factory)["bots"]
    assert [(b["id"], b["role"]) for b in bots] == [
        ("api-1", "web"),
        ("api-2", "web"),
        ("worker", "worker"),
    ]


def test_only_whitelisted_short_fields_survive(factory):
    secret = "user@example.com says hello " + "x" * 200
    snap = {
        "turns": [
            {
                "conv": "abc12345",
                "kind": "chat",
                "message": secret,
                "user_id": "full-user-id",
                "agents": [{"agent": "planner", "phase": "tools", "text": secret}],
            }
        ]
    }
    _beat(factory, snapshot=snap)
    dumped = json.dumps(_aggregate(factory))
    assert "user@example.com" not in dumped and "full-user-id" not in dumped


def test_malformed_snapshot_is_tolerated(factory):
    _beat(factory, pid=1, snapshot={"turns": "nope"})
    _beat(factory, pid=2, snapshot={"turns": [None, {"agents": "x"}]})
    bot = _aggregate(factory)["bots"][0]
    assert bot["agent_count"] == 0


# --- endpoint ---------------------------------------------------------------

_SECRET = "a" * 64


def test_endpoint_returns_no_store_json(client, tmp_db):
    f = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    now = datetime.now(timezone.utc)
    BotHeartbeatRepository(f).upsert(
        instance_id="api-ep",
        pid=1,
        role="web",
        host="h",
        started_at=_iso(now),
        last_seen=_iso(now),
        snapshot={"turns": [_turn("c1", "planner")]},
    )
    try:
        resp = client.get("/dashboard/bots.json")
    finally:
        BotHeartbeatRepository(f).delete("api-ep", 1)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert set(body) == {"generated_at", "bots", "counts"}
    assert body["bots"][0]["id"] == "api-ep"


def test_endpoint_requires_login(tmp_db, monkeypatch):
    settings = Settings(
        dashboard_basic_user="ops",
        dashboard_basic_password="pw",
        dashboard_secret_key=_SECRET,
    )
    monkeypatch.setattr("app.core.dashboard_auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    app = create_app()

    def _session():
        s = get_session_factory(tmp_db)()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session
    c = TestClient(app)
    resp = c.get(
        "/dashboard/bots.json",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    html = c.get(
        "/dashboard/bots.json", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert html.status_code == 303
