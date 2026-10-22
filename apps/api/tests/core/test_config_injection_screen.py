"""Injection-screen settings (specs/agent-injection-screen Task 1.1)."""

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_injection_screen_settings_have_off_defaults(monkeypatch):
    # The Verify command pins this to "" in the environment; drop it so the
    # genuine None default is observable rather than the env override.
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.injection_screen_mode == "off"
    assert s.typesafe_api_key is None
    assert s.injection_screen_model == "jev-1.13.0"
    assert s.injection_screen_base_url == "https://api.typesafe.ai"
    assert s.injection_screen_threshold == 0.7
    assert s.injection_screen_timeout_seconds == 2.0
    assert s.injection_screen_cache_ttl_seconds == 3600
    assert s.injection_screen_cache_max_entries == 2048
    assert s.injection_screen_active is False


def test_injection_screen_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, injection_screen_mode="on")


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_injection_screen_threshold_must_be_a_probability(threshold):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, injection_screen_threshold=threshold)


def test_injection_screen_active_needs_mode_and_key():
    assert (
        Settings(
            _env_file=None, injection_screen_mode="off", typesafe_api_key="k"
        ).injection_screen_active
        is False
    )
    assert (
        Settings(
            _env_file=None, injection_screen_mode="shadow", typesafe_api_key="   "
        ).injection_screen_active
        is False
    )
    assert (
        Settings(
            _env_file=None, injection_screen_mode="shadow", typesafe_api_key="k"
        ).injection_screen_active
        is True
    )
