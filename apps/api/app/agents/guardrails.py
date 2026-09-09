"""Input guardrails (specs/pii-middleware-guardrail).

A pre-model PII guardrail: redacts sensitive PII from the user's turn *before* it
reaches any LLM provider, and — because it runs as the graph's entry node and
replaces the message in place (same id via the ``add_messages`` reducer) — before
it is persisted to the checkpointer or read by the background memory extractor.

Scope is deliberately narrow: **credit card only**. Names are NOT redacted — the
personalization flow (MIN-53) captures the user's name via the post-response
memory extractor, which reads these same messages; redacting names would
silently break it. Phone numbers are also left untouched because booking tools
need the raw contact number. **Email is no longer redacted** (product decision,
close-product-loop-s1-booking-ui): booking cannot complete without an email, and
the assistant now offers the traveller's account email and asks them to confirm
it rather than collecting one blind — a masked ``[REDACTED_EMAIL]`` made that
impossible. Real email addresses therefore now flow into the model, the
checkpointer, and the conversation history, where before they were redacted at
this node and again in the router's ``_turn_input``. This is a plain LangGraph
node, not ``PIIMiddleware`` (that path requires ``create_agent``, which this
project does not use).
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage

from app.agents.state import TravelAgentState

logger = logging.getLogger(__name__)

# A run of 13–19 digits, optionally grouped by single spaces or hyphens (card
# formats). Deliberately broad — spaces, dots, hyphens, and newlines are all
# tolerated as separators; the Luhn window search below is what distinguishes a
# real card from an incidental digit run. The run ends on a digit so a trailing
# separator is never consumed.
_CARD_RUN_RE = re.compile(r"\d[\d\s.\-]{11,}\d")


def _luhn_ok(digits: str) -> bool:
    """Return True if ``digits`` passes the Luhn checksum (real card numbers do).

    Used to keep the card regex from masking arbitrary long digit runs (order
    numbers, IDs) that are not payment cards.

    :param digits: A string of only digit characters.
    :return: Whether the Luhn checksum is valid.
    """
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Card lengths in preference order: the common 16/15/13/14 and 19 first, the
# uncommon 17/18 last. This matters when a card is glued to trailing digits
# (e.g. an expiry) inside one run — checking standard lengths first finds the
# real card before a longer, expiry-inflated window that happens to pass Luhn.
_CARD_LENGTHS = (16, 15, 13, 14, 19, 18, 17)


def _card_last4(digits: str) -> str | None:
    """Return last-4 of a Luhn-valid card window inside a digit run.

    Searches windows (not the whole run) so a card immediately followed by other
    digits — expiry, CVV, a stray number glued by a separator — is still
    detected, the reason a whole-run Luhn check leaked cards. Standard card
    lengths are tried first (see ``_CARD_LENGTHS``).

    :param digits: The digit-only characters of a candidate run.
    :return: The last four digits of a valid card window, or None if none exists.
    """
    n = len(digits)
    for length in _CARD_LENGTHS:
        if length > n:
            continue
        for start in range(n - length + 1):
            window = digits[start : start + length]
            if _luhn_ok(window):
                return window[-4:]
    return None


def _mask_card(match: re.Match[str]) -> str:
    """Mask a candidate run to ``****-****-****-<last4>`` when it holds a card.

    :param match: A regex match over a candidate card-number run.
    :return: The masked form when the run contains a Luhn-valid 13–19 digit card,
        else the original text unchanged.
    """
    raw = match.group(0)
    last4 = _card_last4(re.sub(r"\D", "", raw))
    return f"****-****-****-{last4}" if last4 is not None else raw


def redact_pii(text: str) -> str:
    """Redact credit-card PII from free text.

    Credit card → ``****-****-****-<last4>``. Email is intentionally left
    untouched (product decision: booking needs a real email, and the assistant
    now offers/confirms the traveller's account email instead of collecting one
    blind — see module docstring). Phone numbers and names are also left
    untouched (see module docstring).

    :param text: The raw user text.
    :return: The text with credit-card PII masked.
    """
    if not text:
        return text
    text = _CARD_RUN_RE.sub(_mask_card, text)
    return text


def pii_guardrail_node(state: TravelAgentState) -> dict:
    """Graph entry node: redact PII in the latest user message, in place.

    Finds the most recent ``HumanMessage`` (the new turn) and, if redaction
    changes it, returns a replacement carrying the **same id** so the
    ``add_messages`` reducer overwrites it rather than appending — keeping the
    redacted form out of the checkpointer and out of the post-response extractor.
    No-ops (empty update) when there is no user message, no text content, no PII,
    or no id to replace by.

    :param state: The current graph state; reads ``messages``.
    :return: Partial state update replacing the redacted user message, or ``{}``.
    """
    messages = state.get("messages") or []
    original = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    if original is None or not isinstance(original.content, str) or original.id is None:
        return {}

    redacted = redact_pii(original.content)
    if redacted == original.content:
        return {}

    logger.info("[agent] node=pii_guardrail redacted user input")
    # model_copy keeps the id (so add_messages replaces in place) plus name /
    # additional_kwargs / response_metadata rather than dropping them.
    return {"messages": [original.model_copy(update={"content": redacted})]}
