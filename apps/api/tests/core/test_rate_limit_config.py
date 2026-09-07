"""Rate-limit 429 error + tunable policy settings (specs/rate-limit-primitive T1.2)."""

import pytest
from app.core.config import Settings
from app.exceptions import AppError, RateLimitError
from pydantic import ValidationError


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


@pytest.mark.parametrize(
    "env_key", ["FEEDBACK_RATE_LIMIT_MAX", "FEEDBACK_RATE_LIMIT_WINDOW_SECONDS"]
)
def test_non_positive_rate_limit_settings_rejected_at_startup(monkeypatch, env_key):
    # A misconfigured window of 0 must fail validation at settings load, not
    # blow up with ZeroDivisionError per-request.
    monkeypatch.setenv(env_key, "0")
    with pytest.raises(ValidationError):
        Settings()
