"""Static USD price table (per 1M tokens) for the agent-turn cost estimate — data copied from provider pricing pages, not logic (the unit test pins the formula, never these numbers)."""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Normalized model names already warned about, so a hot path logs each at most once.
_WARNED_UNPRICED: set[str] = set()


class ModelPrice(NamedTuple):
    """USD price per 1M tokens for one model."""

    input: float
    output: float
    cached_input: float


# fmt: off
MODEL_PRICES_USD_PER_1M: dict[str, ModelPrice] = {
    # OpenAI — verified 2026-09-03 developers.openai.com/api/docs/pricing
    #                             input   output  cached_input
    "gpt-5":         ModelPrice(  1.25,   10.00,   0.125),
    "gpt-5-mini":    ModelPrice(  0.25,    2.00,   0.025),
    "gpt-5.5":       ModelPrice(  5.00,   30.00,   0.50),
    "gpt-5.4-mini":  ModelPrice(  0.75,    4.50,   0.075),
    "gpt-5.4-nano":  ModelPrice(  0.20,    1.25,   0.02),
    "gpt-4o-mini":   ModelPrice(  0.15,    0.60,   0.075),
    "gpt-4.1-mini":  ModelPrice(  0.40,    1.60,   0.10),
    # Anthropic — the 5.5 rows verified 2026-10-24 against platform.claude.com/docs/en/about-claude/pricing; the older rows are not re-checked.
    # cache_creation (cache-write) tokens are NOT priced here (no caching in scope).
    # claude-haiku-5-5 is the <=100K-token prompt tier (over 100K the page lists 0.50 / 2.50 / 0.05, not modelled).
    # Opus/Sonnet 5.5 cache hits are 0.05x the input price.
    "claude-opus-5-5":            ModelPrice(4.00, 20.00, 0.20),
    "claude-sonnet-5-5":          ModelPrice(2.00, 10.00, 0.10),
    "claude-haiku-5-5":           ModelPrice(0.10,  0.50, 0.01),
    "claude-opus-4-8":            ModelPrice(5.00, 25.00, 0.50),
    "claude-sonnet-5":            ModelPrice(2.00, 10.00, 0.20),
    "claude-haiku-4-5-20251001":  ModelPrice(1.00,  5.00, 0.10),
    # Google — verified 2026-09-03 ai.google.dev/gemini-api/docs/pricing
    # gemini-2.5-pro is tiered by prompt size; values below are the <=200k-token tier.
    "gemini-2.5-pro":   ModelPrice(1.25, 10.00, 0.125),
    "gemini-2.5-flash": ModelPrice(0.30,  2.50, 0.03),
}
# fmt: on

# Trailing ``-YYYY-MM-DD`` dated-snapshot suffix (e.g. ``gpt-5-2026-01-15``).
_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def normalize_model(name: str) -> str:
    """Reduce a raw model name to its price-table key (strip a ``models/``/``openai/``/``anthropic/`` prefix and a trailing ``-YYYY-MM-DD`` snapshot suffix)."""
    for prefix in ("models/", "openai/", "anthropic/"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    return _SNAPSHOT_RE.sub("", name)


def is_priced(model: str) -> bool:
    """True when ``model`` (after normalization) has an entry in the price table."""
    return normalize_model(model) in MODEL_PRICES_USD_PER_1M


def estimate_cost(by_model: dict[str, dict]) -> float | None:
    """Sum USD cost across per-model token counts (``input_tokens`` already includes the ``cached`` subset); ``None`` when unknown — empty input or a model missing from the price table, since a false ``0.0`` is worse than an explicit unknown."""
    if not by_model:
        return None
    unpriced = [
        m for m in map(normalize_model, by_model) if m not in MODEL_PRICES_USD_PER_1M
    ]
    if unpriced:
        for normalized in unpriced:
            if normalized not in _WARNED_UNPRICED:
                _WARNED_UNPRICED.add(normalized)
                logger.warning(
                    "[pricing] unpriced model %r — run cost recorded as NULL",
                    normalized,
                )
        return None
    total = 0.0
    for model, usage in by_model.items():
        price = MODEL_PRICES_USD_PER_1M[normalize_model(model)]
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cached_tokens = usage.get("cached_tokens", 0)
        total += (
            (input_tokens - cached_tokens) * price.input
            + cached_tokens * price.cached_input
            + output_tokens * price.output
        )
    return total / 1e6
