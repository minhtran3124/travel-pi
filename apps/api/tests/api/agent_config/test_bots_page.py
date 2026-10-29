"""#315: the /dashboard/bots page (server render, login guard, polling hooks, i18n)."""

from datetime import datetime, timedelta, timezone

from app.db.engine import get_session_factory
from app.repositories.bot_heartbeat import BotHeartbeatRepository

from tests.api.agent_config.test_agent_run_detail_page import (
    _build_client,
    _configured_settings,
    _log_in,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def _page(tmp_db, monkeypatch, path="/dashboard/bots", beats=False):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    _log_in(client, settings)
    if beats:
        now = datetime.now(timezone.utc)
        BotHeartbeatRepository(get_session_factory(tmp_db)).upsert(
            instance_id="api-1",
            pid=1,
            role="web",
            host="h",
            started_at=_iso(now - timedelta(hours=1)),
            last_seen=_iso(now),
            snapshot={
                "turns": [
                    {
                        "conv": "c<script>alert(1)</script>",
                        "kind": "chat",
                        "agents": [
                            {
                                "agent": "planner",
                                "phase": "tools",
                                "tool": "search_places",
                                "since": _iso(now - timedelta(seconds=5)),
                            }
                        ],
                    }
                ]
            },
        )
    return client.get(path)


def test_page_renders_empty_state_for_logged_in_user(tmp_db, monkeypatch):
    res = _page(tmp_db, monkeypatch)
    assert res.status_code == 200
    html = res.text
    assert "No bots reporting" in html
    assert 'id="bots-empty" hidden' not in html
    assert 'href="/dashboard/bots"' in html  # nav entry


def test_page_has_polling_hook_filters_and_pause(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch).text
    assert "/dashboard/bots.json" in html
    assert "POLL_MS = 3000" in html
    assert "visibilitychange" in html
    assert 'id="pause-btn"' in html
    assert 'id="f-role"' in html and 'id="f-kind"' in html
    assert "prefers-reduced-motion" in html


def test_page_embeds_snapshot_escaped_and_hides_empty_state(tmp_db, monkeypatch):
    res = _page(tmp_db, monkeypatch, beats=True)
    assert res.status_code == 200
    html = res.text
    assert "api-1" in html
    assert "<script>alert(1)</script>" not in html
    assert 'id="bots-empty" hidden' in html


def test_page_vietnamese_strings(tmp_db, monkeypatch):
    res = _page(tmp_db, monkeypatch, path="/dashboard/bots?lang=vi")
    assert "Chưa có bot nào báo cáo" in res.text
    assert "dashboard_lang=vi" in res.headers.get("set-cookie", "")


def test_page_requires_login(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    res = client.get("/dashboard/bots", follow_redirects=False)
    assert res.status_code in (303, 401)
