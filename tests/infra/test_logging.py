"""Tests for logging configuration and the request-logging middleware."""

import logging

from app.core.config import Settings
from app.core.logging import configure_logging


def test_request_emits_access_log(client, caplog):
    """Every request produces one method/path/status line from app.main."""
    with caplog.at_level(logging.INFO, logger="app.main"):
        client.get("/")
    messages = [r.getMessage() for r in caplog.records]
    assert any("GET /" in m and "200" in m for m in messages)


def test_app_error_is_logged_as_warning(client, caplog):
    """A domain error (404) is logged at WARNING by the exception handler."""
    with caplog.at_level(logging.WARNING, logger="app.main"):
        client.get("/bookings/00000000-0000-0000-0000-000000000000")
    warnings = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any("NotFoundError" in m for m in warnings)


def test_configure_logging_applies_level():
    """configure_logging applies the configured level to the root logger."""
    try:
        configure_logging(Settings(log_level="warning"))
        assert logging.getLogger().level == logging.WARNING
    finally:
        # Restore the INFO default the rest of the suite runs under.
        configure_logging(Settings(log_level="info"))
