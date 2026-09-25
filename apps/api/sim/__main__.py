"""``python -m sim`` — CLI entry point, preflight, and batch orchestration.

Preflight (design §7) fails fast with exit 2 and spends no quota: it refuses a
non-sim base URL without ``--i-know``, a missing ``claude`` binary, an empty
``OPENAI_API_KEY`` in the ``--env-file``, and a base URL that does not answer
``GET /healthz`` — in that order, cheapest first, none of them spawning
``claude``. On a clean preflight it starts the identity and event servers, runs
the batch, grades it, writes the reports, and keeps the bus up so the UI can
show the final state.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

import sim
from sim import personas as personas_mod
from sim.bus import Bus
from sim.db_check import sim_session_factory, snapshot
from sim.driver import run_batch
from sim.grader import grade, write_reports
from sim.keys import KeyServer

BASE_URL_DEFAULT = "http://localhost:8001"
SIM_PORT = 8001
JWKS_PORT = 8766
BUS_PORT = 8765
DB_SIM_URL = "postgresql+psycopg://travel:travel@localhost:5434/travel"
ABORT_STATUSES = {"auth_misconfigured", "tier_misconfigured"}

# Held after batch_end so a late or reconnecting UI can render the final state.
# Tests set it to 0.
BUS_LINGER_SECONDS = 30

_PACKAGE_DIR = Path(sim.__file__).parent
_RUNS_DIR = _PACKAGE_DIR / "runs"
_COMPOSE_FILE = _PACKAGE_DIR.parent / "docker-compose.sim.yml"
_STATIC_DIR = _PACKAGE_DIR.parents[2] / "tools" / "sim-ui"
_DEFAULT_ENV_FILE = _PACKAGE_DIR.parent / ".env"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m sim")
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--personas", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--i-know", action="store_true")
    parser.add_argument("--env-file", type=Path, default=_DEFAULT_ENV_FILE)
    return parser.parse_args(argv)


def _openai_key(env_file: Path) -> str | None:
    if not env_file.is_file():
        return None
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "OPENAI_API_KEY":
            return value.strip().strip("'\"")
    return None


def _healthz_ok(base_url: str) -> bool:
    try:
        response = httpx.get(base_url.rstrip("/") + "/healthz", timeout=5.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _preflight(args: argparse.Namespace) -> str | None:
    port = urlparse(args.base_url).port
    if port != SIM_PORT and not args.i_know:
        return (
            f"base URL port {port!r} is not the sim port {SIM_PORT}; "
            "pass --i-know to override (guards the dev database)"
        )
    if shutil.which(os.environ.get("SIM_CLAUDE_BIN", "claude")) is None:
        return "claude binary not found (set SIM_CLAUDE_BIN or add it to PATH)"
    if not _openai_key(args.env_file):
        return f"OPENAI_API_KEY is empty or missing in {args.env_file}"
    if not _healthz_ok(args.base_url):
        return f"{args.base_url} did not answer GET /healthz"
    return None


def _set_tier(persona_id: str) -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "travel-sim",
            "-f",
            str(_COMPOSE_FILE),
            "exec",
            "-T",
            "api-sim",
            "python",
            "-m",
            "scripts.set_tier",
            f"sim-{persona_id}",
            "premium",
        ],
        check=True,
        timeout=60,
    )


def _print_checklist(status: str) -> None:
    if status == "auth_misconfigured":
        print(
            "batch aborted (401): check the JWKS server and issuer.\n"
            "  - SUPABASE_JWKS_URL must point at the sim JWKS server "
            f"(host.docker.internal:{JWKS_PORT}).\n"
            "  - SUPABASE_JWT_ISSUER must be 'sim'.",
            file=sys.stderr,
        )
    else:
        print(
            "batch aborted (429): premium-tier setup failed. Re-run tier setup "
            "and confirm api-sim can reach db-sim.",
            file=sys.stderr,
        )


def _verdict_counts(grades) -> dict:
    counts: dict = {}
    for g in grades:
        key = g.verdict if g.graded else "ungraded"
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _grade_all(batch, bus, since_floor) -> list:
    factory = sim_session_factory(DB_SIM_URL)
    grades = []
    for session in batch.sessions:
        since = session.started_at or since_floor
        rows = snapshot(factory, f"sim-{session.persona.id}", since)
        result = await grade(session, rows)
        grades.append(result)
        if result.graded:
            await bus.publish(
                {
                    "type": "session_graded",
                    "persona_id": result.persona_id,
                    "score": result.score,
                    "verdict": result.verdict,
                }
            )
    return grades


async def _run(args: argparse.Namespace) -> int:
    run_dir = _RUNS_DIR / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    keys = KeyServer(port=JWKS_PORT)
    keys.start()
    bus = Bus(run_dir, _STATIC_DIR, port=BUS_PORT)
    await bus.start()
    print(f"UI: http://localhost:{bus.port}/")

    exit_code = 0
    try:
        if args.personas is not None:
            personas = personas_mod.load(args.personas)
        else:
            personas = await personas_mod.generate(args.n, args.seed, out_dir=run_dir)

        await bus.publish(
            {
                "type": "batch_start",
                "persona_id": None,
                "v": 1,
                "personas": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "country_code": p.country_code,
                        "language": p.language,
                    }
                    for p in personas
                ],
                "seats": args.parallel,
            }
        )

        since_floor = datetime.now(timezone.utc)
        async with httpx.AsyncClient() as client:
            batch = await run_batch(
                personas,
                args.parallel,
                args.base_url,
                keys,
                bus,
                client,
                _set_tier,
            )

        if batch.status in ABORT_STATUSES:
            _print_checklist(batch.status)
            summary = {
                "status": batch.status,
                "sessions": len(batch.sessions),
                "claude_calls": batch.claude_calls,
            }
            exit_code = 1
        else:
            grades = await _grade_all(batch, bus, since_floor)
            write_reports(run_dir, batch, grades)
            summary = {
                "status": batch.status,
                "sessions": len(batch.sessions),
                "verdicts": _verdict_counts(grades),
                "claude_calls": batch.claude_calls,
            }

        await bus.publish({"type": "batch_end", "persona_id": None, "summary": summary})
        await asyncio.sleep(BUS_LINGER_SECONDS)
    finally:
        await bus.stop()
        keys.stop()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    problem = _preflight(args)
    if problem is not None:
        print(f"preflight failed: {problem}", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
