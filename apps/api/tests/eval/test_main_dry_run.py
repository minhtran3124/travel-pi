"""`python -m eval --dry-run` must work with zero provider keys in the
environment (agent-eval-pipeline task 1.1).

Runs the real entrypoint as a subprocess (not an in-process import) so it
sees no leftover key from this test process's own environment, and clears
every provider key to an *empty string* rather than unsetting it — an unset
var lets `.env` (via `python-dotenv`) refill it, an empty one does not.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APPS_API_DIR = Path(__file__).resolve().parents[2]


def test_dry_run_lists_smoke_goldens_without_any_provider_key() -> None:
    env = {
        **os.environ,
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "GOOGLE_API_KEY": "",
    }

    result = subprocess.run(
        [sys.executable, "-m", "eval", "--suite", "smoke", "--dry-run"],
        cwd=APPS_API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "routing-happy-en-01" in result.stdout
