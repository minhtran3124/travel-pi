import os
import subprocess
import sys
from pathlib import Path

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
    assert result.stderr == ""
