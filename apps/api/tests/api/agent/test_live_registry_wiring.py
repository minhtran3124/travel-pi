"""Chat and stream turns feed the live registry and always leave it empty afterwards."""

from app.agents import live_registry as lr
from fastapi.testclient import TestClient
from tests.api.agent.test_agent_run_steps_wiring import _make_app


def _record_registry(monkeypatch):
    seen: list[str] = []
    original = lr.LiveRegistry.set_agent

    def spy(self, run_id, key, agent, phase, tool=None):
        seen.append(agent)
        return original(self, run_id, key, agent, phase, tool)

    monkeypatch.setattr(lr.LiveRegistry, "set_agent", spy)
    return seen


def test_chat_turn_is_visible_then_cleared(tmp_path, monkeypatch):
    lr.registry.clear()  # idle sessions outlive a turn, so start from an empty process-wide registry
    seen = _record_registry(monkeypatch)
    with TestClient(_make_app(tmp_path)) as c:
        resp = c.post("/agent/chat", json={"message": "see Tokyo", "user_id": "u1"})
    assert resp.status_code == 200
    assert {"supervisor", "concierge"} <= set(seen)
    snap = lr.registry.snapshot()
    assert (
        snap["turns"] == []
    )  # the turn is over; the chat stays listed as an idle session
    assert len(snap["sessions"]) == 1


def test_stream_turn_is_visible_then_cleared(tmp_path, monkeypatch):
    lr.registry.clear()  # idle sessions outlive a turn, so start from an empty process-wide registry
    seen = _record_registry(monkeypatch)
    with TestClient(_make_app(tmp_path)) as c:
        resp = c.post("/agent/stream", json={"message": "hi", "user_id": "u1"})
        assert "event: done" in resp.text
    assert "supervisor" in seen
    snap = lr.registry.snapshot()
    assert snap["turns"] == []
    assert len(snap["sessions"]) == 1
