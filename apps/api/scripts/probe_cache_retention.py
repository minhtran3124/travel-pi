#!/usr/bin/env python3
"""Two-phase A/B prompt-cache retention probe (specs/prompt-caching-system-prefix Task 2.2).

Settle one question a sloppier one-armed probe could not: does OpenAI's
``prompt_cache_retention="24h"`` actually keep a prompt prefix cached across a
long idle gap? A single ``24h`` arm proves nothing — the DEFAULT ``in_memory``
policy already survives "5 to 10 minutes of inactivity, up to one hour", so a hit
after 21 minutes sits inside *both* windows. This probe therefore runs **two
arms** over separately nonced prompts — ``24h`` and an ``in_memory`` control —
and refuses to report until the idle gap is at least ``--min-gap-min`` (default
60), the bucket where the project's own data shows a 0/17 hit rate.

Two mutually exclusive phases:

    # 1. seed: warm each arm's cache (two calls per arm so the write lands)
    python -m scripts.probe_cache_retention --seed
    # ... wait >= 60 minutes, doing nothing to these threads ...
    # 2. check: re-send each prompt once, compare cache reads, print a verdict
    python -m scripts.probe_cache_retention --check

The verdict is a single token on its own last line:

    RETENTION-WINS  only the 24h arm read cached tokens (the parameter works)
    TIE             both arms read cached tokens (cannot attribute to 24h)
    BOTH-MISS       neither arm read cached tokens (cache expired for both)
    CONTROL-ONLY    only the in_memory control read cached tokens — an anomaly
                    (not a retention win, not a tie, not both-miss); reported
                    distinctly so it can never be mislabelled

Exit codes:

    0  a verdict was reached (--check), or both arms seeded warm (--seed)
    2  --check ran too soon: the idle gap is under --min-gap-min
    3  the probe cannot produce a trustworthy verdict and must be re-seeded —
       either a --seed arm's second call read 0 cached tokens (the write never
       landed: parameter ignored, model lacks the policy, or a routing miss), or
       --check found the state already carries a check attempt (a check refreshes
       the cache, so any prior attempt — finished OR crashed partway through the
       arms — restarts the idle clock it just reset)

``--seed`` sends each arm TWICE and verifies the second call read cached tokens;
if either arm's second read is 0 it refuses to write the state file (exit 3), so
a later ``--check`` can never mistake a write that never landed for an expired
cache (``BOTH-MISS``).

!!! WARNING: a cache READ refreshes the entry's idle timer. Every ``--check``
therefore restarts the idle clock, so a naive re-check appears to "succeed"
forever — and so does a re-check after a check that crashed after touching only
the first arm. To close both, ``--check`` stamps an ``attempted_at`` marker into
the state AFTER the gap gate but BEFORE the first invoke, and persists it before
any call; it then refuses (exit 3) against any state that already carries an
attempt, finished or not. A repeat measurement needs a fresh ``--seed``.

Calls ``_build_chat_model("openai", model, model_kwargs={"prompt_cache_retention":
value})`` directly, so the probe stays independent of any settings flag a later
task may add. Cache reads are pulled from
``usage_metadata["input_token_details"]["cache_read"]`` — the same path
``app/agents/metrics.py`` uses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from app.clients.llm import _build_chat_model
from app.core.config import get_settings

# The two retention arms. ``in_memory`` is OpenAI's documented default policy and
# serves as the control: without it, a hit cannot be attributed to ``24h``.
RETENTION_24H = "24h"
RETENTION_CONTROL = "in_memory"
ARMS = (RETENTION_24H, RETENTION_CONTROL)

# apps/api/ root (scripts/ lives directly under it), so the default state path is
# stable regardless of the caller's working directory.
_API_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = _API_ROOT / ".harness-state" / "cache_retention_probe.json"

# Filler large enough to make a cacheable prefix (~5-6k tokens ≈ 27k chars).
_FILLER = (
    "Traveller planning notes for cache-retention measurement. "
    "This paragraph is deliberately verbose so the prompt prefix is long "
    "enough for the provider to cache it. "
) * 170


def _build_prompt(nonce: str) -> str:
    """A deterministic ~5-6k-token prompt keyed by *nonce* (rebuilt on check)."""
    return f"[probe-nonce:{nonce}]\n{_FILLER}\nSummarise the notes above in one word."


def _cache_read(message: Any) -> int:
    """Read cached-prompt tokens the way ``app/agents/metrics.py`` does."""
    usage = getattr(message, "usage_metadata", None)
    details = (usage or {}).get("input_token_details") or {}
    return int(details.get("cache_read", 0) or 0)


def _input_tokens(message: Any) -> int:
    usage = getattr(message, "usage_metadata", None)
    return int((usage or {}).get("input_tokens", 0) or 0)


def _model_for(value: str, model: str) -> Any:
    return _build_chat_model(
        "openai", model, model_kwargs={"prompt_cache_retention": value}
    )


def seed(state_path: Path, model: str) -> int:
    """Warm each arm's cache with a fresh nonce; store nonces + a timestamp.

    Each arm is sent TWICE: the first call writes the prefix, the second call is
    what proves the cache write actually landed. The second call's cache_read is
    printed per arm; if EITHER arm read 0 cached tokens the write never landed
    (parameter ignored, model lacks the policy, or a routing miss), so no state
    file is written and the probe exits 3 — otherwise a later ``--check`` would
    read that never-warmed arm as ``BOTH-MISS`` and call it an expired cache.

    Returns the process exit code: 3 if an arm was not warmed, else 0.
    """
    # Remove any state file from a PREVIOUS seed before making any call. A seed
    # that refuses a cold arm or crashes midway must not leave the old run's
    # nonces + clock behind for a later --check to trust as this run.
    state_path.unlink(missing_ok=True)

    arms: dict[str, dict[str, str]] = {}
    second_reads: dict[str, int] = {}
    for value in ARMS:
        nonce = uuid.uuid4().hex
        prompt = _build_prompt(nonce)
        chat = _model_for(value, model)
        message: Any = None
        for _ in range(2):
            message = chat.invoke(prompt)
        second_reads[value] = _cache_read(message)
        arms[value] = {"nonce": nonce}
        print(
            f"seeded arm {value!r} nonce={nonce} "
            f"second_call_cache_read={second_reads[value]}"
        )

    cold = [value for value in ARMS if second_reads[value] <= 0]
    if cold:
        print(
            f"seed did NOT warm arm(s) {cold}: the second call read 0 cached "
            "tokens, so the write never landed (parameter ignored, model lacks "
            "the policy, or a routing miss). Refusing to write the state file; "
            "the probe must be re-seeded."
        )
        return 3

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"model": model, "seeded_at": time.time(), "arms": arms}, indent=2
        )
    )
    print(f"wrote state {state_path}")
    return 0


def check(state_path: Path, min_gap_min: float) -> int:
    """Re-send each nonced prompt once; print per-arm reads and a verdict.

    Returns the process exit code: 3 if the state was already checked (a check
    refreshes the cache, so a second check restarts the idle clock and cannot be
    trusted), 2 while the idle gap is under *min_gap_min* (too soon to attribute
    anything), 0 once a verdict is reached.
    """
    state = json.loads(state_path.read_text())

    if "attempted_at" in state or "checked_at" in state:
        print(
            "this state file already carries a check attempt (a cache read "
            "refreshes the idle timer, so any check — even one that crashed "
            "after touching only the first arm — restarts the clock it just "
            "reset and would report a false result forever). Re-seed before "
            "checking again."
        )
        return 3

    model = state["model"]
    elapsed_min = (time.time() - state["seeded_at"]) / 60.0

    if elapsed_min < min_gap_min:
        print(
            f"elapsed {elapsed_min:.1f} min < min gap {min_gap_min:.0f} min; "
            "wait longer before checking (a check refreshes the cache — "
            "re-seed if you have already checked)."
        )
        return 2

    # The experiment is spent the moment ANY arm's cache is touched. Stamp an
    # attempt marker now — AFTER the gap gate, BEFORE the first invoke — and
    # persist it, so if a later arm's call raises (network error, 5xx, timeout)
    # the already-refreshed first arm cannot be re-measured: the next --check
    # sees the marker and refuses (exit 3), whether this run finishes or crashes.
    state["attempted_at"] = time.time()
    state_path.write_text(json.dumps(state, indent=2))

    hits: dict[str, bool] = {}
    for value in ARMS:
        nonce = state["arms"][value]["nonce"]
        message = _model_for(value, model).invoke(_build_prompt(nonce))
        cached = _cache_read(message)
        hit = cached > 0
        hits[value] = hit
        print(
            f"arm={value} input={_input_tokens(message)} cache_read={cached} "
            f"{'HIT' if hit else 'MISS'} elapsed={elapsed_min:.1f}min"
        )

    # Mark the check complete. The attempt marker above already blocks a re-check;
    # checked_at records that the run also finished, for the state file's reader.
    state["checked_at"] = time.time()
    state_path.write_text(json.dumps(state, indent=2))

    print(_verdict(hits[RETENTION_24H], hits[RETENTION_CONTROL]))
    return 0


def _verdict(retention_hit: bool, control_hit: bool) -> str:
    """Map the two arms' hit/miss to a verdict token.

    ``CONTROL-ONLY`` covers the anomalous case where only the default policy
    read cache — it is not a tie, not both-miss, and certainly not a retention
    win, so it is reported distinctly rather than mislabelled.
    """
    if retention_hit and control_hit:
        return "TIE"
    if retention_hit and not control_hit:
        return "RETENTION-WINS"
    if not retention_hit and not control_hit:
        return "BOTH-MISS"
    return "CONTROL-ONLY"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Two-phase A/B OpenAI prompt-cache retention probe."
    )
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--seed", action="store_true", help="Warm both arms' caches.")
    phase.add_argument("--check", action="store_true", help="Measure and verdict.")
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE,
        help="State file path (default: apps/api/.harness-state/cache_retention_probe.json).",
    )
    parser.add_argument(
        "--model", default=None, help="Model (default: settings.llm_model)."
    )
    parser.add_argument(
        "--min-gap-min",
        type=float,
        default=60.0,
        help="Minimum idle minutes before --check will verdict (default 60).",
    )
    args = parser.parse_args()

    if args.seed:
        model = args.model or get_settings().llm_model
        sys.exit(seed(args.state, model))

    sys.exit(check(args.state, args.min_gap_min))


if __name__ == "__main__":
    main()
