"""The only caller of ``claude -p`` (design §5.1).

Spawns ``claude -p`` in a fresh temp dir with a fixed flag set, parses its
``stream-json`` output, exposes the latest quota gauge, and maps usage limits
and malformed output to ``QuotaExhausted`` / ``DriverError``.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

DEFAULT_TIMEOUT = 120


class QuotaExhausted(Exception):
    """A usage or rate limit was hit."""


class DriverError(Exception):
    """The CLI failed, timed out, or returned unusable output."""


@dataclass
class Quota:
    five_hour: float | None
    seven_day: float | None
    resets_at: str | None


last_quota: Quota | None = None


def _binary() -> str:
    return os.environ.get("SIM_CLAUDE_BIN", "claude")


def _build_args(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    model: str | None,
) -> list[str]:
    resolved_model = model or os.environ.get("SIM_CLAUDE_MODEL", "sonnet")
    return [
        _binary(),
        "-p",
        user_prompt,
        "--system-prompt",
        system_prompt,
        "--model",
        resolved_model,
        "--tools",
        "",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--setting-sources",
        "",
        "--output-format",
        "stream-json",
        "--verbose",
        "--json-schema",
        json.dumps(schema),
    ]


def _parse_events(text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []
    try:
        whole = json.loads(text)
    except json.JSONDecodeError:
        whole = None
    if isinstance(whole, list):
        return [event for event in whole if isinstance(event, dict)]
    if isinstance(whole, dict):
        return [whole]
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            # A malformed line is skipped; a run is judged by its result event.
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _update_quota(event: dict) -> str | None:
    global last_quota
    info = event.get("rate_limit_info", {})
    windows = info.get("unifiedWindows", {})
    last_quota = Quota(
        five_hour=windows.get("five_hour", {}).get("utilization"),
        seven_day=windows.get("seven_day", {}).get("utilization"),
        resets_at=info.get("resetsAt"),
    )
    return info.get("status")


def _is_rate_limit_error(result: dict) -> bool:
    subtype = str(result.get("subtype", ""))
    return subtype.startswith("error_rate") or subtype == "error_usage_limit"


async def run(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    args = _build_args(system_prompt, user_prompt, schema, model)
    cwd = tempfile.mkdtemp(prefix="sim-claude-")
    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except (FileNotFoundError, PermissionError) as exc:
            raise DriverError(f"could not launch claude binary {_binary()!r}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            proc.kill()
            await proc.wait()
            raise DriverError("claude -p timed out") from exc
    finally:
        shutil.rmtree(cwd, ignore_errors=True)

    events = _parse_events(stdout.decode())
    rate_event = next((e for e in events if e.get("type") == "rate_limit_event"), None)
    result = next((e for e in events if e.get("type") == "result"), None)

    if rate_event is not None:
        status = _update_quota(rate_event)
        # Only an outright rejection exhausts quota; warning-level statuses
        # (e.g. ``allowed_warning``) still run.
        if status == "rejected":
            raise QuotaExhausted(f"rate limit status: {status}")

    if proc.returncode not in (0, None):
        if (
            result is not None
            and result.get("is_error")
            and _is_rate_limit_error(result)
        ):
            raise QuotaExhausted("rate limit reported on a failed run")
        tail = stderr.decode(errors="replace")[-500:]
        raise DriverError(f"claude -p exited with code {proc.returncode}: {tail}")

    if result is None:
        raise DriverError("no result event in claude output")

    if result.get("is_error"):
        if _is_rate_limit_error(result):
            raise QuotaExhausted("rate limit reported in result event")
        raise DriverError("claude -p returned an error result")

    output = result.get("structured_output")
    if not isinstance(output, dict):
        raise DriverError("result carried no structured_output object")
    return output


def cli_version() -> str:
    try:
        proc = subprocess.run(
            [_binary(), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise DriverError(f"could not launch claude binary {_binary()!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DriverError(f"claude --version timed out for {_binary()!r}") from exc
    return proc.stdout.strip()
