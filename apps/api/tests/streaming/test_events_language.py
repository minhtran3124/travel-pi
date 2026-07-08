import json

from app.streaming import events


def test_panel_defaults_language_en():
    ev = events.panel(tool_call_id="t1", kind="weather", data={})
    assert json.loads(ev.data)["language"] == "en"


def test_panel_carries_language():
    ev = events.panel(tool_call_id="t1", kind="weather", data={}, language="vi")
    assert json.loads(ev.data)["language"] == "vi"


def test_done_carries_language():
    ev = events.done(conversation_id="c1", current_flow="concierge", language="vi")
    assert json.loads(ev.data)["language"] == "vi"
