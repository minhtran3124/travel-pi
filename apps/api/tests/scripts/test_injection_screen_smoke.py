import os
import subprocess
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[2]


def test_exits_2_with_one_stdout_line_when_key_blank():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.injection_screen_smoke"],
        cwd=API_DIR,
        env={
            **os.environ,
            "TYPESAFE_API_KEY": "",
            "DATABASE_URL": "sqlite:///:memory:",
        },
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 2
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines == ["TYPESAFE_API_KEY is not set"]
    assert "Traceback" not in result.stderr


def test_exits_3_when_any_item_unscreened(monkeypatch):
    from app.services import injection_screen_service
    from app.services.injection_screen_service import Verdict
    from scripts import injection_screen_smoke

    settings = injection_screen_smoke.get_settings().model_copy(
        update={"typesafe_api_key": "ts-key"}
    )
    monkeypatch.setattr(injection_screen_smoke, "get_settings", lambda: settings)

    async def fake_screen(items):
        return [Verdict(False, False, None, None)]

    monkeypatch.setattr(injection_screen_service, "screen", fake_screen)

    with pytest.raises(SystemExit) as exc:
        injection_screen_smoke.main()

    assert exc.value.code == 3
