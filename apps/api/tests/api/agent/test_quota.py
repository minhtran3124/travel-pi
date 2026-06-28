"""Quota guard tests — D4 (specs/runtime-context-config).

Covers:
- free user under limit → 200
- free user at/over limit → 429 with clear message
- premium user over limit → 200 (unlimited)
- yesterday's turns don't count toward today's quota

Uses FakeLLM + in-memory graph (offline). Mirrors the _make_app harness from
test_agent_chat.py. The limit is patched to 2 via monkeypatch so tests don't
need to POST 20 times.
"""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user_optional
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.routers.agent import get_travel_graph
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LIMIT = 2  # patched value; avoids 20 real POSTs


def _make_app(tmp_path, *, premium_users: list[str] | None = None):
    """Build a test app with an isolated SQLite DB and FakeLLM graph."""
    from app.repositories.user import UserRepository

    url = f"sqlite:///{tmp_path / 'quota_test.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    if premium_users:
        s = get_session_factory(url)()
        try:
            for uid in premium_users:
                UserRepository(s).upsert_tier(uid, "premium")
            s.commit()
        finally:
            s.close()

    app = create_app()

    def _override_session():
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 20,
        responses=["Hello!"] * 20,
    )
    fast = FakeLLM(responses=["OK"] * 20)
    _graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: _graph

    # Premium requires authentication (anonymous is always free under hybrid identity).
    # Simulate being logged in as the first premium user so tier resolves correctly.
    if premium_users:
        _puid = premium_users[0]
        app.dependency_overrides[get_current_user_optional] = lambda: AuthUser(
            id=_puid, email=None, role=None, claims={}
        )

    return app, url


def _seed_user_turns(url: str, user_id: str, count: int) -> None:
    """Seed *count* user-role messages for *user_id* dated today (UTC)."""
    from app.db import models
    from app.db.base import new_uuid

    s = get_session_factory(url)()
    try:
        conv = models.Conversation(id=new_uuid(), user_id=user_id)
        s.add(conv)
        s.flush()
        for _ in range(count):
            s.add(
                models.Message(
                    id=new_uuid(),
                    conversation_id=conv.id,
                    role="user",
                    content="test",
                )
            )
        s.commit()
    finally:
        s.close()


def _seed_yesterday_turn(url: str, user_id: str) -> None:
    """Seed one user message with a yesterday created_at string."""
    from datetime import datetime, timedelta, timezone

    from app.db import models
    from app.db.base import new_uuid

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    yesterday_iso = yesterday.isoformat()

    s = get_session_factory(url)()
    try:
        conv = models.Conversation(id=new_uuid(), user_id=user_id)
        s.add(conv)
        s.flush()
        msg = models.Message(
            id=new_uuid(),
            conversation_id=conv.id,
            role="user",
            content="yesterday",
        )
        msg.created_at = yesterday_iso
        s.add(msg)
        s.commit()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_free_user_under_limit_is_allowed(tmp_path, monkeypatch):
    """Free user with 0 turns today → 200."""
    monkeypatch.setattr(
        "app.services.quota_service.get_settings",
        lambda: type("S", (), {"agent_free_daily_turn_limit": _LIMIT})(),
    )
    app, _ = _make_app(tmp_path)
    with TestClient(app) as c:
        resp = c.post("/agent/chat", json={"message": "hi", "user_id": "u_free"})
    assert resp.status_code == 200


def test_free_user_at_limit_gets_429(tmp_path, monkeypatch):
    """Free user with turns_today == limit → 429 with clear message."""
    monkeypatch.setattr(
        "app.services.quota_service.get_settings",
        lambda: type("S", (), {"agent_free_daily_turn_limit": _LIMIT})(),
    )
    app, url = _make_app(tmp_path)
    _seed_user_turns(url, "u_free", _LIMIT)  # exactly at the limit

    with TestClient(app) as c:
        resp = c.post("/agent/chat", json={"message": "hi", "user_id": "u_free"})

    assert resp.status_code == 429
    body = resp.json()
    assert "limit" in body["message"].lower() or "daily" in body["message"].lower()


def test_free_user_over_limit_stream_gets_429(tmp_path, monkeypatch):
    """Free user over limit → 429 on /stream before streaming begins."""
    monkeypatch.setattr(
        "app.services.quota_service.get_settings",
        lambda: type("S", (), {"agent_free_daily_turn_limit": _LIMIT})(),
    )
    app, url = _make_app(tmp_path)
    _seed_user_turns(url, "u_free", _LIMIT + 1)

    with TestClient(app) as c:
        resp = c.post("/agent/stream", json={"message": "hi", "user_id": "u_free"})

    assert resp.status_code == 429


def test_premium_user_over_limit_is_allowed(tmp_path, monkeypatch):
    """Premium user with turns_today > limit → 200 (unlimited)."""
    monkeypatch.setattr(
        "app.services.quota_service.get_settings",
        lambda: type("S", (), {"agent_free_daily_turn_limit": _LIMIT})(),
    )
    app, url = _make_app(tmp_path, premium_users=["u_premium"])
    _seed_user_turns(url, "u_premium", _LIMIT + 5)

    with TestClient(app) as c:
        resp = c.post("/agent/chat", json={"message": "hi", "user_id": "u_premium"})

    assert resp.status_code == 200


def test_yesterday_turns_dont_count(tmp_path, monkeypatch):
    """A message from yesterday must not count toward today's quota."""
    monkeypatch.setattr(
        "app.services.quota_service.get_settings",
        lambda: type("S", (), {"agent_free_daily_turn_limit": _LIMIT})(),
    )
    app, url = _make_app(tmp_path)
    # Seed limit-1 turns from yesterday; today's count is 0.
    for _ in range(_LIMIT):
        _seed_yesterday_turn(url, "u_free")

    with TestClient(app) as c:
        resp = c.post("/agent/chat", json={"message": "hi", "user_id": "u_free"})

    assert resp.status_code == 200
