"""#310: the dashboard defaults to the light Daylight theme with the paper palette."""

import re

from tests.api.agent_config.test_agent_run_detail_page import (
    _build_client,
    _configured_settings,
    _log_in,
)

PALETTE = {
    "--bg": "#f4f1ea",
    "--panel": "#fbf9f4",
    "--nav": "#efebe2",
    "--panel-2": "#ece7dc",
    "--ink": "#1d1a15",
    "--muted": "#5e584d",
    "--line": "#d9d3c6",
}


def _page(tmp_db, monkeypatch) -> str:
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    _log_in(client, settings)
    res = client.get("/dashboard/agent-runs")
    assert res.status_code == 200
    return res.text


def test_html_ships_daylight_server_side(tmp_db, monkeypatch):
    # Rendered on <html> so first paint is light, not only set from JS.
    assert '<html lang="en" data-theme="daylight">' in _page(tmp_db, monkeypatch)


def test_daylight_uses_demo_paper_palette(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch)
    block = html.split('html[data-theme="daylight"] {', 1)[1].split("}", 1)[0]
    for token, value in PALETTE.items():
        assert re.search(rf"{token}:\s*{value}\b", block), token


def test_stored_choice_wins_and_os_preference_is_ignored(tmp_db, monkeypatch):
    html = _page(tmp_db, monkeypatch)
    assert "prefers-color-scheme" not in html
    assert "t === 'sunset' || t === 'nightfall' || t === 'daylight'" in html
