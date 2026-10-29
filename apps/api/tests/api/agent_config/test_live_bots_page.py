"""GET /dashboard/live-bots: server-rendered shell of the live bots page (SQLite)."""

from tests.api.agent_config.test_live_bots_json import (
    env,  # noqa: F401  (shared fixture)
)

_URL = "/dashboard/live-bots"


def test_page_renders_empty_state_without_js(env):  # noqa: F811
    client, _ = env
    resp = client.get(_URL)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "No bots running" in body
    assert 'id="lb-empty"' in body
    # No bot cards are server-rendered: the grid is filled by the poller.
    assert 'id="lb-grid"' in body
    assert "lb-card s-" not in body


def test_page_has_polling_hook_and_filter_chips(env):  # noqa: F811
    client, _ = env
    body = client.get(_URL).text
    assert "/dashboard/live-bots.json" in body
    assert "visibilitychange" in body  # polling pauses when the tab is hidden
    assert 'id="lb-pause"' in body
    for kind in (
        "all",
        "planner",
        "concierge",
        "journal",
        "booking",
        "budget",
        "research",
    ):
        assert f'data-filter="{kind}"' in body
    assert "prefers-reduced-motion" in body


def test_nav_links_to_live_bots(env):  # noqa: F811
    client, _ = env
    assert 'href="/dashboard/live-bots"' in client.get(_URL).text


def test_page_language_switch(env):  # noqa: F811
    client, _ = env
    vi = client.get(_URL, params={"lang": "vi"}).text
    assert "Chưa có bot nào đang chạy" in vi
    assert "No bots running" not in vi
    assert "No bots running" in client.get(_URL, params={"lang": "en"}).text


def test_page_requires_dashboard_login(env):  # noqa: F811
    client, _ = env
    client.cookies.clear()
    resp = client.get(_URL, headers={"accept": "text/html"}, follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "/dashboard/login" in resp.headers["location"]
