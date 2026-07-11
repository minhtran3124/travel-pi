from app.core.config import get_settings
from app.routers.agent import _resolve_timezone


def test_valid_timezone_passthrough():
    assert _resolve_timezone("Asia/Ho_Chi_Minh") == "Asia/Ho_Chi_Minh"


def test_invalid_timezone_falls_back_to_default():
    assert _resolve_timezone("Not/AZone") == get_settings().agent_timezone


def test_missing_timezone_falls_back_to_default():
    assert _resolve_timezone(None) == get_settings().agent_timezone
