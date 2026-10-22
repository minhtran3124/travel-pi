#!/usr/bin/env python3
"""Two-phase A/B probe: does OpenAI's ``prompt_cache_retention="24h"`` keep a prefix
cached across a long idle gap?

Runs two nonced arms — ``24h`` and an ``in_memory`` control — because a single arm
cannot attribute a hit to ``24h`` (the default policy also survives short gaps).
Two mutually exclusive phases::

    python -m scripts.probe_cache_retention --seed   # warm both arms
    # ... wait >= --min-gap-min minutes, doing nothing to these threads ...
    python -m scripts.probe_cache_retention --check  # measure and verdict

Verdict (single token on the last line): RETENTION-WINS (only 24h hit),
TIE (both hit), BOTH-MISS (neither hit), CONTROL-ONLY (only control hit — anomaly).

Exit codes: 0 verdict reached / both arms seeded warm; 2 ``--check`` too soon;
3 must re-seed (a seed arm's write never landed, or the state already carries a
check attempt). A cache READ refreshes the idle timer, so ``--check`` stamps an
``attempted_at`` marker before any call and refuses any already-attempted state —
otherwise a re-check would restart the clock and appear to succeed forever.
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

# ``in_memory`` is the control arm: without it a hit cannot be attributed to 24h.
RETENTION_24H = "24h"
RETENTION_CONTROL = "in_memory"
ARMS = (RETENTION_24H, RETENTION_CONTROL)

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

    Each arm is sent twice so the second call can prove the write landed; if
    either arm still reads 0 cached tokens no state is written and it exits 3,
    else a later ``--check`` would misread that arm as an expired cache.
    """
    # Drop any previous seed's state before calling, so a refused or crashed
    # seed cannot leave stale nonces + clock for a later --check to trust.
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
        json.dumps({"model": model, "seeded_at": time.time(), "arms": arms}, indent=2)
    )
    print(f"wrote state {state_path}")
    return 0


def check(state_path: Path, min_gap_min: float) -> int:
    """Re-send each nonced prompt once; print per-arm reads and a verdict.

    Exits 3 if the state was already checked, 2 while the idle gap is under
    *min_gap_min*, 0 once a verdict is reached.
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

    # Stamp the attempt marker after the gap gate but before the first invoke:
    # once any arm's cache is touched the experiment is spent, so a later --check
    # must refuse (exit 3) even if this run crashes mid-way.
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

    # Record that the run finished, for the state file's reader.
    state["checked_at"] = time.time()
    state_path.write_text(json.dumps(state, indent=2))

    print(_verdict(hits[RETENTION_24H], hits[RETENTION_CONTROL]))
    return 0


def _verdict(retention_hit: bool, control_hit: bool) -> str:
    """Map the two arms' hit/miss to a verdict token."""
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
