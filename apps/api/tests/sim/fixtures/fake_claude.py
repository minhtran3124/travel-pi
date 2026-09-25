#!/usr/bin/env python3
"""Offline stand-in for the real ``claude`` binary, driven by env vars.

Replaces ``claude`` in tests through ``SIM_CLAUDE_BIN``. It records its argv,
optionally counts calls, and emits ``stream-json`` lines chosen by
``$FAKE_CLAUDE_MODE`` (``ok``, ``rate_limited``, ``error_rate_limit``,
``bad_json``, ``array_shape``, ``warn``, ``mixed``).
"""

from __future__ import annotations

import json
import os
import sys


def _write_argv() -> None:
    path = os.environ.get("FAKE_CLAUDE_ARGV_FILE")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sys.argv[1:], fh)


def _record_call() -> None:
    path = os.environ.get("FAKE_CLAUDE_CALLS_FILE")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("call\n")


def _structured_output() -> object:
    path = os.environ.get("FAKE_CLAUDE_OUTPUT_FILE")
    if not path:
        return {"ok": True}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        return data
    idx_path = path + ".idx"
    index = 0
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            index = int(fh.read() or "0")
    value = data[index] if index < len(data) else data[-1]
    with open(idx_path, "w", encoding="utf-8") as fh:
        fh.write(str(index + 1))
    return value


def _rate_limit_event(status: str) -> dict:
    five_hour = float(os.environ.get("FAKE_CLAUDE_FIVE_HOUR", "0.4"))
    seven_day = float(os.environ.get("FAKE_CLAUDE_SEVEN_DAY", "0.33"))
    return {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": status,
            "resetsAt": "2026-09-25T12:00:00Z",
            "unifiedWindows": {
                "five_hour": {"utilization": five_hour},
                "seven_day": {"utilization": seven_day},
            },
        },
    }


def _emit(events: list[dict]) -> None:
    for event in events:
        sys.stdout.write(json.dumps(event) + "\n")


def main() -> int:
    if "--version" in sys.argv[1:]:
        sys.stdout.write("1.2.3 (Claude Code)\n")
        return 0

    _write_argv()
    _record_call()

    sleep = float(os.environ.get("FAKE_CLAUDE_SLEEP", "0"))
    if sleep:
        import time

        time.sleep(sleep)

    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    system = {"type": "system", "subtype": "init", "apiKeySource": "none"}

    if mode == "rate_limited":
        _emit(
            [
                system,
                _rate_limit_event("rejected"),
                {"type": "result", "subtype": "error_rate_limit", "is_error": True},
            ]
        )
        return 1

    if mode == "error_other":
        sys.stderr.write("fatal: agent stopped after max turns\n")
        _emit(
            [
                system,
                _rate_limit_event("allowed"),
                {"type": "result", "subtype": "error_max_turns", "is_error": True},
            ]
        )
        return 1

    if mode == "error_rate_limit":
        # Status stays allowed; the rate limit surfaces only in the error result.
        _emit(
            [
                system,
                _rate_limit_event("allowed"),
                {"type": "result", "subtype": "error_rate_limit", "is_error": True},
            ]
        )
        return 1

    if mode == "bad_json":
        _emit([system, _rate_limit_event("allowed")])
        # A genuinely malformed line, and no valid result event.
        sys.stdout.write('{"type": "result", not-json\n')
        return 0

    if mode == "warn":
        _emit(
            [
                system,
                _rate_limit_event("allowed_warning"),
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "structured_output": _structured_output(),
                },
            ]
        )
        return 0

    result = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": _structured_output(),
        "result": "done",
        "usage": {"input_tokens": 1044, "output_tokens": 12},
    }

    if mode == "array_shape":
        sys.stdout.write(
            json.dumps([system, _rate_limit_event("allowed"), result]) + "\n"
        )
        return 0

    if mode == "mixed":
        _emit([system, _rate_limit_event("allowed")])
        sys.stdout.write("this line is not json\n")
        _emit([result])
        return 0

    _emit([system, _rate_limit_event("allowed"), result])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
