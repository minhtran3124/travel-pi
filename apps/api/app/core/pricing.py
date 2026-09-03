"""Static USD price table for the agent-turn cost estimate.

Prices are **data, not logic**: each per-provider block is copied verbatim from
the provider's public pricing page on the date in its header comment, and the
unit test pins the *formula* (via a monkeypatched fake price), never these
numbers. Re-verify and bump the header date when a provider changes a price.

Scope notes:

* Anthropic ``cache_creation`` (5-minute cache-*write*, billed at 1.25x input)
  is **not** priced here — no ``cache_control`` is in use in this app, so no
  turn accrues cache-write tokens. Only cache *reads* (``cached_input``) are
  priced. Revisit if prompt caching is turned on.
* Gemini 2.5 Pro is tiered by prompt size; this table records the **≤200k-token
  tier** only. A flat per-1M table cannot express the >200k tier, and turns in
  this app stay well under 200k.

Covers every model in ``LLM_PROVIDERS[*].models`` (after normalisation — the
``clinepass`` gateway names models ``openai/<model>``) plus the two config
defaults ``gpt-5`` / ``gpt-5-mini``.
"""

from __future__ import annotations

import re
from typing import NamedTuple


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
    # Anthropic — verified 2026-09-03 platform.claude.com/docs/en/about-claude/pricing
    # cache_creation (cache-write) tokens are NOT priced here (no caching in scope).
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
    """Reduce a raw model name to its price-table key.

    Strips a leading ``models/`` or ``openai/`` prefix (the ``clinepass``
    gateway names models ``openai/<model>``) and a trailing dated-snapshot
    suffix ``-YYYY-MM-DD``.

    :param name: The raw model name as reported by the SDK / catalogue.
    :return: The normalised key to look up in ``MODEL_PRICES_USD_PER_1M``.
    """
    for prefix in ("models/", "openai/"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    return _SNAPSHOT_RE.sub("", name)


def estimate_cost(by_model: dict[str, dict]) -> float | None:
    """Sum the USD cost across per-model token counts.

    For each model: ``((input - cached) * p_in + cached * p_cached +
    output * p_out) / 1e6``, where ``input_tokens`` already includes the
    ``cached_tokens`` subset (OpenAI/LangChain semantics).

    :param by_model: Maps a model name to a dict with ``input_tokens``,
        ``output_tokens`` and ``cached_tokens`` (each defaulting to 0).
    :return: Total cost in USD, or ``None`` when the cost is unknown — either
        no usage was captured at all (empty ``by_model``) or some model
        normalises to a name absent from the price table. A partial or
        falsely-confident ``0.0`` is worse than an explicit unknown.
    """
    if not by_model:
        return None
    total = 0.0
    for model, usage in by_model.items():
        price = MODEL_PRICES_USD_PER_1M.get(normalize_model(model))
        if price is None:
            return None
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cached_tokens = usage.get("cached_tokens", 0)
        total += (
            (input_tokens - cached_tokens) * price.input
            + cached_tokens * price.cached_input
            + output_tokens * price.output
        )
    return total / 1e6
