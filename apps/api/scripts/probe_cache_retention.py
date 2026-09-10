#!/usr/bin/env python3
"""Two-phase A/B prompt-cache retention probe (specs/prompt-caching-system-prefix Task 2.2).

Settle one question a sloppier one-armed probe could not: does OpenAI's
``prompt_cache_retention="24h"`` actually keep a prompt prefix cached across a
long idle gap? A single ``24h`` arm proves nothing — the DEFAULT ``in_memory``
policy already survives "5 to 10 minutes of inactivity, up to one hour", so a hit
after 21 minutes sits inside *both* windows. This probe therefore runs **two
arms** over separately nonced prompts — ``24h`` and an ``in_memory`` control —
and refuses to report until the idle gap exceeds ``--min-gap-min`` (default 60),
the bucket where the project's own data shows a 0/17 hit rate.

Two mutually exclusive phases:

    # 1. seed: warm each arm's cache (two calls per arm so the write lands)
    python -m scripts.probe_cache_retention --seed
    # ... wait > 60 minutes, doing nothing to these threads ...
    # 2. check: re-send each prompt once, compare cache reads, print a verdict
    python -m scripts.probe_cache_retention --check

The verdict is a single token on its own last line:

    RETENTION-WINS  only the 24h arm read cached tokens (the parameter works)
    TIE             both arms read cached tokens (cannot attribute to 24h)
    BOTH-MISS       neither arm read cached tokens (cache expired for both)

``--check`` exits 0 once a verdict is reached and 2 when the elapsed gap is still
under ``--min-gap-min``.

!!! WARNING: a cache READ refreshes the entry's idle timer. Every ``--check``
therefore restarts the idle clock, so a naive re-check appears to "succeed"
forever. A repeat measurement needs a fresh ``--seed`` — never re-``--check`` the
same state file and trust the second reading.

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

# Filler large enough to make a cacheable prefix (~3k tokens ≈ 12k chars).
_FILLER = (
    "Traveller planning notes for cache-retention measurement. "
    "This paragraph is deliberately verbose so the prompt prefix is long "
    "enough for the provider to cache it. "
) * 170


def _build_prompt(nonce: str) -> str:
    """A deterministic ~3k-token prompt keyed by *nonce* (rebuilt on check)."""
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


def seed(state_path: Path, model: str) -> None:
    """Warm each arm's cache with a fresh nonce; store nonces + a timestamp.

    Each arm is sent TWICE: the first call writes the prefix, the second call is
    what proves the cache write actually landed before we walk away to wait.
    """
    arms: dict[str, dict[str, str]] = {}
    for value in ARMS:
        nonce = uuid.uuid4().hex
        prompt = _build_prompt(nonce)
        chat = _model_for(value, model)
        for _ in range(2):
            chat.invoke(prompt)
        arms[value] = {"nonce": nonce}
        print(f"seeded arm {value!r} nonce={nonce}")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"model": model, "seeded_at": time.time(), "arms": arms}, indent=2
        )
    )
    print(f"wrote state {state_path}")


def check(state_path: Path, min_gap_min: float) -> int:
    """Re-send each nonced prompt once; print per-arm reads and a verdict.

    Returns the process exit code: 2 while the idle gap is under *min_gap_min*
    (too soon to attribute anything), 0 once a verdict is reached.
    """
    state = json.loads(state_path.read_text())
    model = state["model"]
    elapsed_min = (time.time() - state["seeded_at"]) / 60.0

    if elapsed_min < min_gap_min:
        print(
            f"elapsed {elapsed_min:.1f} min < min gap {min_gap_min:.0f} min; "
            "wait longer before checking (a check refreshes the cache — "
            "re-seed if you have already checked)."
        )
        return 2

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
        seed(args.state, model)
        sys.exit(0)

    sys.exit(check(args.state, args.min_gap_min))


if __name__ == "__main__":
    main()
