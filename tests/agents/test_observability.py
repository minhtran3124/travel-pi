"""Langfuse observability wiring (specs/travel-agent Task 7.1)."""


def test_handler_none_when_disabled():
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.agents.observability import build_langfuse_handler, callbacks

    assert build_langfuse_handler() is None
    assert callbacks() == []


def test_handler_built_when_enabled(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.agents.observability import build_langfuse_handler, callbacks

    handler = build_langfuse_handler()
    assert handler is not None
    cbs = callbacks()
    assert len(cbs) == 1
    get_settings.cache_clear()


def test_trace_metadata_groups_by_user_and_trip():
    from app.agents.observability import trace_metadata

    meta = trace_metadata("u1", "t1")
    assert meta["langfuse_user_id"] == "u1"
    assert meta["langfuse_session_id"] == "t1"
    assert "travel-agent" in meta["langfuse_tags"]

    # missing trip -> 'none' session
    assert trace_metadata("u1", None)["langfuse_session_id"] == "none"
