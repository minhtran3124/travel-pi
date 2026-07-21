"""Rate-limit 429 error + tunable policy settings (specs/rate-limit-primitive T1.2)."""

import pytest
from app.core.config import Settings
from app.exceptions import AppError, RateLimitError


def test_rate_limit_error_is_429_and_carries_retry_after():
    err = RateLimitError("slow down", retry_after=42)
    assert isinstance(err, AppError)
    assert err.status_code == 429
    assert err.retry_after == 42
    assert err.detail == "slow down"


def test_rate_limit_error_default_detail():
    err = RateLimitError(retry_after=1)
    assert "Rate limit" in err.detail


def test_retry_after_is_required_keyword():
    with pytest.raises(TypeError):
        RateLimitError("no retry_after")  # type: ignore[call-arg]


def test_feedback_rate_limit_settings_have_safe_defaults():
    s = Settings()
    assert s.feedback_rate_limit_max == 30
    assert s.feedback_rate_limit_window_seconds == 60


def test_feedback_rate_limit_settings_env_overridable(monkeypatch):
    monkeypatch.setenv("FEEDBACK_RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("FEEDBACK_RATE_LIMIT_WINDOW_SECONDS", "10")
    s = Settings()
    assert s.feedback_rate_limit_max == 5
    assert s.feedback_rate_limit_window_seconds == 10
