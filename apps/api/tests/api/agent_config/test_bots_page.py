"""#315: the /dashboard/bots page (server render, login guard, polling hooks, i18n)."""

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
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


def test_page_has_mascot_motion_hooks(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch).text
    assert html.count("@media (prefers-reduced-motion: reduce) {\n    *, *::before, *::after { animation: none") == 1
    for kf in ("bots-bob", "bots-blink", "bots-wiggle", "bots-pulse"):
        assert f"@keyframes {kf}" in html
    assert "toggle('is-busy'" in html
    assert ".bot-card.is-busy .mascot" in html
    assert ".bot-card.is-stale .mascot" in html
    assert 'class="eye"' in html and 'class="acc"' in html
    assert "setAttribute('data-phase'" in html
    assert ".agent[data-phase=tools] .mascot" in html
    assert 'role="img" aria-label="' in html


def test_page_has_hero_ids_and_no_meters(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch).text
    for cid in ("k-online", "k-busy", "k-agents", "k-turns"):
        assert f'id="{cid}"' in html
    assert 'class="meter' not in html and "hero-meter" not in html


def test_page_defines_friendly_name_helper(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch).text
    assert "function friendlyName(" in html
    assert "friendly-names:start" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_friendly_name_is_deterministic(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch).text
    block = re.search(
        r"/\* friendly-names:start \*/(.*?)/\* friendly-names:end \*/", html, re.S
    )
    assert block, "friendly-names block missing"
    script = block.group(1) + (
        "console.log(JSON.stringify(["
        "friendlyName('planner','abc'),friendlyName('planner','abc'),"
        "friendlyName('planner','abd'),friendlyName('nope','abc')]));"
    )
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    a, b, _c, d = json.loads(proc.stdout)
    assert a == b
    assert isinstance(d, str) and d


def test_page_turns_collapse_and_cap(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch).text
    assert "aria-expanded" in html and "turn-sum" in html
    assert "function applyTurnCap(" in html and "TURN_CAP = 4" in html
    assert "work-more" in html and '"more_turns"' in html
    assert "max-height: 420px" in html
