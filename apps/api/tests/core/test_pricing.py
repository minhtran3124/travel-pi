"""Tests for the static price table + cost estimate (SC-3).

The formula is pinned with a *fake* price injected via monkeypatch, so the
assertions do not silently track (or ossify) the real published numbers — those
live in ``pricing.py`` and are re-verified by a human against the pricing page.
"""

from __future__ import annotations

import pytest
from app.core import pricing
from app.core.llm_providers import LLM_PROVIDERS
from app.core.pricing import ModelPrice, estimate_cost, normalize_model


@pytest.fixture
def fake_table(monkeypatch):
    """Replace the price table with a single round-numbered fake model."""
    table = {"fake": ModelPrice(input=10.0, output=20.0, cached_input=1.0)}
    monkeypatch.setattr(pricing, "MODEL_PRICES_USD_PER_1M", table)
    return table


def test_formula_no_cache(fake_table):
    # input 1e6, output 1e6, no cache: (1e6 * 10 + 1e6 * 20) / 1e6 = 30.0
    cost = estimate_cost(
        {"fake": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
    )
    assert cost == pytest.approx(30.0)


def test_cached_tokens_are_discounted(fake_table):
    # 1e6 input of which all cached, no output:
    #   ((1e6 - 1e6) * 10 + 1e6 * 1) / 1e6 = 1.0  (cached price, not input price)
    cached = estimate_cost(
        {"fake": {"input_tokens": 1_000_000, "cached_tokens": 1_000_000}}
    )
    uncached = estimate_cost({"fake": {"input_tokens": 1_000_000}})
    assert cached == pytest.approx(1.0)
    assert uncached == pytest.approx(10.0)
    assert cached < uncached  # cache read is cheaper than fresh input


def test_partial_cache_splits_price(fake_table):
    # 1e6 input, 250k cached: (750k*10 + 250k*1) / 1e6 = 7.75
    cost = estimate_cost(
        {"fake": {"input_tokens": 1_000_000, "cached_tokens": 250_000}}
    )
    assert cost == pytest.approx(7.75)


def test_unknown_model_returns_none(fake_table):
    assert estimate_cost({"not-in-table": {"input_tokens": 100}}) is None


def test_any_unknown_model_poisons_the_total(fake_table):
    # a priced model alongside an unpriced one still yields None
    assert (
        estimate_cost(
            {
                "fake": {"input_tokens": 1_000_000},
                "mystery": {"input_tokens": 1_000_000},
            }
        )
        is None
    )


def test_empty_by_model_is_zero(fake_table):
    assert estimate_cost({}) == pytest.approx(0.0)


def test_normalize_dated_snapshot():
    assert normalize_model("gpt-5-2026-01-15") == "gpt-5"


def test_normalize_openai_prefix():
    assert normalize_model("openai/gpt-4o-mini") == "gpt-4o-mini"


def test_normalize_models_prefix():
    assert normalize_model("models/gemini-2.5-pro") == "gemini-2.5-pro"


def test_normalize_prefix_and_snapshot_together():
    assert normalize_model("openai/gpt-5-2026-01-15") == "gpt-5"


def test_dated_snapshot_resolves_to_base_price():
    # normalisation lets a dated snapshot hit the base model's real price
    assert estimate_cost({"gpt-5-2026-01-15": {"input_tokens": 1_000_000}}) is not None


def test_every_catalogue_model_is_priced():
    for profile in LLM_PROVIDERS.values():
        for model in profile.models:
            assert normalize_model(model) in pricing.MODEL_PRICES_USD_PER_1M, (
                f"unpriced catalogue model: {model!r}"
            )


def test_config_defaults_are_priced():
    for model in ("gpt-5", "gpt-5-mini"):
        assert model in pricing.MODEL_PRICES_USD_PER_1M
