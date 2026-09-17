"""Pre-model PII guardrail: redacts credit-card numbers only, at the graph entry node.

Names, phones and emails are left untouched: the memory extractor reads names,
booking needs the raw phone and email, so redacting them would break those flows.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage

from app.agents.state import TravelAgentState

logger = logging.getLogger(__name__)

# Broad candidate run; the Luhn window search below distinguishes a real card
# from an incidental digit run. Ends on a digit so a trailing separator isn't consumed.
_CARD_RUN_RE = re.compile(r"\d[\d\s.\-]{11,}\d")


def _luhn_ok(digits: str) -> bool:
    """Return True if ``digits`` passes the Luhn checksum, so non-card digit runs are spared."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Common lengths first, so a card glued to trailing digits (e.g. an expiry) is
# matched before a longer, inflated window that happens to pass Luhn.
_CARD_LENGTHS = (16, 15, 13, 14, 19, 18, 17)


def _card_last4(digits: str) -> str | None:
    """Return last-4 of a Luhn-valid card window inside a digit run, else None.

    Searches windows, not the whole run, so a card followed by expiry/CVV digits
    is still detected (a whole-run Luhn check leaked those cards).
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
    """Mask a candidate run to ``****-****-****-<last4>`` when it holds a card."""
    raw = match.group(0)
    last4 = _card_last4(re.sub(r"\D", "", raw))
    return f"****-****-****-{last4}" if last4 is not None else raw


def redact_pii(text: str) -> str:
    """Redact credit-card PII from free text; email, phone and names are left untouched."""
    if not text:
        return text
    text = _CARD_RUN_RE.sub(_mask_card, text)
    return text


def pii_guardrail_node(state: TravelAgentState) -> dict:
    """Graph entry node: redact PII in the latest user message in place (same id so
    ``add_messages`` overwrites, keeping the raw form out of the checkpointer)."""
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
    # model_copy keeps the id (so add_messages replaces in place) and metadata.
    return {"messages": [original.model_copy(update={"content": redacted})]}
