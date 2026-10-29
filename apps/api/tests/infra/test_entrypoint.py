"""docker/entrypoint.sh: migrations are opt-in via RUN_MIGRATIONS=1."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

DOCKER_DIR = Path(__file__).resolve().parents[2] / "docker"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="sh not available")


def _run(tmp_path: Path, run_migrations: str | None) -> tuple[str, str]:
    """Run the entrypoint with a fake `alembic` on PATH; return (alembic calls, stdout)."""
    calls = tmp_path / "alembic.calls"
    fake = tmp_path / "alembic"
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env.pop("RUN_MIGRATIONS", None)
    if run_migrations is not None:
        env["RUN_MIGRATIONS"] = run_migrations
    res = subprocess.run(
        [SH, str(DOCKER_DIR / "entrypoint.sh"), "echo", "served"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return (calls.read_text() if calls.exists() else ""), res.stdout


@pytest.mark.parametrize("value", [None, "0", ""])
def test_migrations_skipped_unless_opted_in(tmp_path, value):
    calls, out = _run(tmp_path, value)
    assert calls == ""
    assert "served" in out


def test_migrations_run_when_opted_in(tmp_path):
    calls, out = _run(tmp_path, "1")
    assert calls.strip() == "upgrade head"
    assert "served" in out


def test_start_web_uses_gunicorn_with_safe_timeout():
    script = (DOCKER_DIR / "start-web.sh").read_text()
    assert "uvicorn.workers.UvicornWorker" in script
    assert "WEB_CONCURRENCY:-2" in script
    assert "GUNICORN_TIMEOUT:-180" in script  # >= 150s so a 120s LLM call survives
    assert "--reload" not in script
