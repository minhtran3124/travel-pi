"""The GH-180 routing-report checker must discriminate, and must not rot.

`scripts/check_gh180_routing_report.py` is the re-runnable evidence behind this
spec's claim that the two ``routing-multi_turn`` goldens stop crashing. Nothing
else in the suite executes it, so without this module a later edit could quietly
turn it into a script that always exits 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
CHECKER = API_ROOT / "scripts" / "check_gh180_routing_report.py"
PRE_FIX = API_ROOT / "tests" / "fixtures" / "eval" / "gh180_pre_fix_routing_report.json"
POST_FIX = API_ROOT / "eval" / "reports" / "gh180-routing.json"


def _run(path: Path) -> int:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(path)],
        capture_output=True,
        text=True,
    ).returncode


def test_checker_rejects_the_pre_fix_report():
    assert _run(PRE_FIX) == 1


@pytest.mark.skipif(
    not POST_FIX.exists(), reason="post-fix eval report not present in this checkout"
)
def test_checker_accepts_the_post_fix_report():
    assert _run(POST_FIX) == 0


def test_checker_rejects_a_non_validation_crash(tmp_path: Path):
    # A turn that dies with TypeError is still a dead turn. Gating only on the
    # literal string "ValidationError" would report green for exactly the
    # regression this spec guards against.
    report = {
        "schema_version": "1.0",
        "run_meta": {},
        "per_case": [
            {
                "golden_id": f"routing-multi_turn-{lang}-01",
                "capability": "routing",
                "passed": False,
                "checks": [
                    {
                        "name": "agent_run",
                        "passed": False,
                        "detail": "agent run raised TypeError: unhashable type: 'list'",
                    }
                ],
            }
            for lang in ("en", "vi")
        ],
    }
    path = tmp_path / "crashed.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert _run(path) == 1


def test_checker_rejects_a_report_with_too_few_goldens(tmp_path: Path):
    report = {
        "schema_version": "1.0",
        "run_meta": {},
        "per_case": [
            {
                "golden_id": "routing-multi_turn-en-01",
                "capability": "routing",
                "passed": True,
                "checks": [{"name": "flow_match", "passed": True, "detail": None}],
            }
        ],
    }
    path = tmp_path / "thin.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert _run(path) == 1
