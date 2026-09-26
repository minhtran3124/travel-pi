"""_build_chat_model forwards a configurable request timeout that bounds a stalled provider call."""

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def _patch(monkeypatch, *, timeout=120.0):
    """Patch init_chat_model + settings (llm_timeout_seconds=*timeout*); return the captured kwargs dict."""
    captured: dict = {}

    def fake_init(model, **kwargs):
        captured.update(kwargs)
        captured["model"] = model
        return object()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {"llm_base_url": None, "llm_timeout_seconds": timeout},
        )(),
    )
    return captured


def test_timeout_default_is_120_for_openai(monkeypatch):
    captured = _patch(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "m")
    assert captured["timeout"] == 120.0
    assert Settings.model_fields["llm_timeout_seconds"].default == 120.0


def test_timeout_follows_settings_override(monkeypatch):
    captured = _patch(monkeypatch, timeout=45.0)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "m")
    assert captured["timeout"] == 45.0


def test_explicit_timeout_kwarg_wins(monkeypatch):
    captured = _patch(monkeypatch, timeout=120.0)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "m", timeout=5.0)
    assert captured["timeout"] == 5.0


@pytest.mark.parametrize("provider", ["anthropic", "google_genai"])
def test_timeout_applied_for_other_providers(monkeypatch, provider):
    captured = _patch(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model(provider, "m")
    assert captured["timeout"] == 120.0


def test_invalid_non_positive_timeout_rejected():
    with pytest.raises(ValidationError):
        Settings(llm_timeout_seconds=0)
