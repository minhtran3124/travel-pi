"""Input guardrails (MIN-62 / specs/pii-guardrail-redaction).

A pre-model PII guardrail: redacts sensitive PII from the user's turn *before* it
reaches any LLM provider, and — because it runs as the graph's entry node and
replaces the message in place (same id via the ``add_messages`` reducer) — before
it is persisted to the checkpointer or read by the background memory extractor.

Scope is deliberately narrow (MIN-62, confirmed): **email** and **credit card**
only. Names are NOT redacted — the personalization flow (MIN-53) captures the
user's name via the post-response memory extractor, which reads these same
messages; redacting names would silently break it. This is a plain function/node,
not ``PIIMiddleware`` (that path is deferred with the create_agent migration).
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage

from app.agents.state import TravelAgentState

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# A run of 13–19 digits, optionally grouped by single spaces or hyphens (card
# formats). Separators sit only *between* digits so the match never consumes a
# trailing space. The Luhn check below rejects non-card numbers that happen to match.
_CARD_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


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


def _mask_card(match: re.Match[str]) -> str:
    """Mask a matched card number to ``****-****-****-<last4>``; leave non-cards.

    :param match: A regex match over a candidate card-number run.
    :return: The masked form when the run is a Luhn-valid 13–19 digit card, else
        the original text unchanged.
    """
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if not (13 <= len(digits) <= 19) or not _luhn_ok(digits):
        return raw
    return f"****-****-****-{digits[-4:]}"


def redact_pii(text: str) -> str:
    """Redact email and credit-card PII from free text.

    Email → ``[REDACTED_EMAIL]``; credit card → ``****-****-****-<last4>``.
    Phone numbers and names are intentionally left untouched (see module docstring).

    :param text: The raw user text.
    :return: The text with email and card PII redacted/masked.
    """
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _CARD_RE.sub(_mask_card, text)
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
    return {"messages": [HumanMessage(content=redacted, id=original.id)]}
