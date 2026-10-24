"""LLM extractor: the production `Extractor` for `OracleFactCheck` (agent-eval-
pipeline follow-up wiring task).

Implements `evalkit.metrics.oracle.Extractor` — per
`docs/solutions/agent/llm-parses-code-computes.md`, the model here ONLY
*parses* free text into fields; it is never asked whether those fields are
correct. `OracleFactCheck` alone decides agreement, by comparing the dict
this module returns against `DbOracle.lookup()`'s output — this module never
sees the oracle's expected values.

One pydantic schema per oracle `kind`, chosen with field names that mirror
`eval.adapters.db_oracle.DbOracle.lookup()`'s return keys for that kind
EXACTLY — a mismatch here would silently degrade `OracleFactCheck` to "no
claimed value found" (indistinguishable from a genuine hallucination) rather
than raising. `tests/eval/test_extractor.py` pins this mapping against the
real oracle output.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.clients.llm import _build_chat_model, get_fast_llm
from app.core.config import get_settings
from app.core.llm_providers import default_model_for
from evalkit.metrics.oracle import ExtractionError
from pydantic import BaseModel, Field

from eval.adapters.config import EXTRACTOR_MODEL, JUDGE_MODEL_ANTHROPIC

logger = logging.getLogger(__name__)


class _FlightOffersClaim(BaseModel):
    """Claimed values for a `flight_offers` check. Field names match
    `DbOracle._flight_offers()`'s return keys (`count`, `min_price`,
    `max_price`) — `currency` is deliberately omitted: it is rarely stated
    explicitly in a reply, so extracting it would manufacture mismatches.
    """

    count: int | None = Field(
        default=None,
        description="How many flight offers the reply states, or null if not stated.",
    )
    min_price: float | None = Field(
        default=None,
        description="The cheapest price (in USD) the reply states, or null if not stated.",
    )
    max_price: float | None = Field(
        default=None,
        description=(
            "The most expensive price (in USD) the reply states, or null if not stated."
        ),
    )


class _HotelAvailabilityClaim(BaseModel):
    """Claimed values for a `hotel_availability` check. Field names match
    `DbOracle._hotel_availability()`'s return keys exactly.
    """

    nights: int | None = Field(
        default=None,
        description="Number of nights the reply states, or null if not stated.",
    )
    hotel_count: int | None = Field(
        default=None,
        description="Total number of hotels the reply states, or null if not stated.",
    )
    available_count: int | None = Field(
        default=None,
        description="Number of AVAILABLE hotels the reply states, or null if not stated.",
    )
    min_total_price: float | None = Field(
        default=None,
        description=(
            "The cheapest total stay price (in USD) the reply states, or null if not stated."
        ),
    )


class _FxRateClaim(BaseModel):
    """Claimed values for an `fx_rate` check. Field names match
    `DbOracle._fx_rate()`'s return keys exactly.
    """

    rate: float | None = Field(
        default=None,
        description="The exchange rate the reply states, or null if not stated.",
    )
    converted: float | None = Field(
        default=None,
        description="The converted amount the reply states, or null if not stated.",
    )


class _TripBudgetClaim(BaseModel):
    """Claimed values for a `trip_budget` check. Field names match
    `DbOracle._trip_budget()`'s return keys exactly.
    """

    total_cap: float | None = Field(
        default=None,
        description="The total budget cap the reply states, or null if not stated.",
    )
    total_spent: float | None = Field(
        default=None,
        description="The total amount spent the reply states, or null if not stated.",
    )
    total_remaining: float | None = Field(
        default=None,
        description="The remaining budget the reply states, or null if not stated.",
    )
    over_budget: bool | None = Field(
        default=None,
        description="Whether the reply states the trip is over budget, or null if not stated.",
    )


# Kind -> schema. Keep in lockstep with `DbOracle._KINDS`
# (`eval/adapters/db_oracle.py`) — `tests/eval/test_extractor.py` pins each
# schema's field names as a subset of that kind's real `lookup()` keys.
_SCHEMAS: dict[str, type[BaseModel]] = {
    "flight_offers": _FlightOffersClaim,
    "hotel_availability": _HotelAvailabilityClaim,
    "fx_rate": _FxRateClaim,
    "trip_budget": _TripBudgetClaim,
}

_EXTRACTION_PROMPT = (
    "You are extracting facts that an assistant's reply STATES about a travel "
    "search or booking result. You are NOT verifying, computing, or judging "
    "whether those facts are correct — only reading what the text says.\n\n"
    "For each field below, return exactly the value the reply states. "
    "If the reply does not state a value for a field, return null for that "
    "field. Never guess, infer, round, compute, or fill in a value the reply "
    "does not contain.\n\n"
    "Reply:\n{reply}"
)


def _extractor_llm() -> Any:
    if os.environ.get("EVAL_JUDGE_PROVIDER") == "anthropic":
        return _build_chat_model("anthropic", JUDGE_MODEL_ANTHROPIC)
    return _extractor_llm_default()


def _extractor_llm_default() -> Any:
    """The extractor model: the configured fast model, kept on OpenAI when the agent under test is not.

    The extractor is judge-side infrastructure; `--provider anthropic` switches only the agent, so
    sending `EXTRACTOR_MODEL` (an OpenAI model id) to Anthropic would 404.
    """
    if get_settings().llm_provider == "openai":
        return get_fast_llm(EXTRACTOR_MODEL)
    return _build_chat_model(
        "openai", EXTRACTOR_MODEL or default_model_for("openai", fast=True)
    )


def llm_extract(reply: str, kind: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the values *reply* claims for oracle check *kind*.

    Satisfies `evalkit.metrics.oracle.Extractor`. *params* (the oracle-check
    lookup params) are accepted for protocol compatibility and logging
    context only — they are never passed into the prompt, so the model can
    never see the expected answer to parrot back.

    :param reply: The agent's free-text reply to extract claimed facts from.
    :param kind: The oracle check kind (e.g. ``"flight_offers"``); selects the
        extraction schema.
    :param params: The oracle-check's lookup params (unused by extraction
        itself — logging only).
    :return: A dict of the fields the reply actually stated (nulls dropped),
        or `None` when the reply stated nothing at all — a verdict about the
        agent, and the ONLY thing `None` may mean.
    :raises ExtractionError: when extraction could not run (unsupported kind,
        or the LLM call failed) — an eval-config bug, never charged to the agent.
    """
    schema = _SCHEMAS.get(kind)
    if schema is None:
        # The oracle supports this kind but no extraction schema covers it —
        # a vocabulary gap in the eval, not a claim the agent failed to make.
        raise ExtractionError(
            f"no extraction schema for oracle kind={kind!r} — add one to "
            f"eval/adapters/extractor.py::_SCHEMAS"
        )

    llm = _extractor_llm()
    structured = llm.with_structured_output(schema)
    prompt = _EXTRACTION_PROMPT.format(reply=reply)

    try:
        result = structured.invoke(prompt)
    except Exception as exc:
        # Loud, not silent: returning None here would read as "the reply stated
        # nothing", failing the case and blaming a possibly-correct agent for
        # the eval's own broken model/key. See `ExtractionError`'s docstring.
        raise ExtractionError(
            f"extractor LLM call failed for kind={kind} params={params} "
            f"(model={EXTRACTOR_MODEL or 'env FAST_LLM_MODEL default'}): {exc}"
        ) from exc

    claimed = result.model_dump(exclude_none=True)
    return claimed or None
