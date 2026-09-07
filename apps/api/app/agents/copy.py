"""Code-authored agent replies, served in the conversation language.

A handful of replies are written by Python, not the LLM (the tier-gate upgrade
notice, unknown intent, HITL cancel/approve, the error fallback), so they bypass
the prompt-level language rule. ``system_reply`` closes that gap: English (the
default language) is the single source text in ``app/agents/constants.py``;
any other language is translated ONCE by ``ContentTranslationService`` and
cached in ``content_translations`` (``entity_type="system_copy"``), so no
per-language table is ever hand-maintained. Every failure — no DB, translator
error, LLM outage — serves the English source; this never raises.
"""

from __future__ import annotations

import hashlib
import logging

from pydantic import BaseModel

from app.agents.constants import (
    AGENT_ERROR_FALLBACK_MSG,
    BOOKING_UPGRADE_MSG,
    NOT_SURE_MSG,
    PLAN_APPROVED_MSG,
    PLAN_CANCELLED_MSG,
)
from app.core.languages import DEFAULT_LANGUAGE, normalize
from app.services.content_translation_service import (
    ContentTranslationService,
    Translator,
)
from app.tools._base import session_scope

logger = logging.getLogger(__name__)

#: Translation-store entity kind for system copy (rows keyed by copy key).
ENTITY_TYPE = "system_copy"

#: Stable key → English source text. Add a message here (and in constants.py);
#: never add a per-language variant.
SYSTEM_COPY: dict[str, str] = {
    "booking_upgrade": BOOKING_UPGRADE_MSG,
    "unknown_intent": NOT_SURE_MSG,
    "booking_cancelled": PLAN_CANCELLED_MSG,
    "plan_approved": PLAN_APPROVED_MSG,
    "agent_error_fallback": AGENT_ERROR_FALLBACK_MSG,
}


class _Copy(BaseModel):
    id: str
    text: str


def system_reply(
    key: str, language: str | None, *, translator: Translator | None = None
) -> str:
    """Return the system copy for ``key`` in ``language``.

    :param key: A ``SYSTEM_COPY`` key.
    :param language: Conversation language; unknown/empty → default → English.
    :param translator: Test seam; ``None`` uses the LLM translator.
    :return: The translated text, or the English source on any failure.
    :raises KeyError: For a key missing from ``SYSTEM_COPY`` (programmer error).
    """
    source = SYSTEM_COPY[key]
    if normalize(language) == DEFAULT_LANGUAGE:
        return source
    # The cache row is keyed by key + a digest of the English source, so editing
    # a constant invalidates its translations instead of serving a stale one.
    row_id = f"{key}:{hashlib.sha1(source.encode()).hexdigest()[:10]}"
    try:
        with session_scope() as s:
            [out] = ContentTranslationService(s, translator).localize(
                ENTITY_TYPE, [_Copy(id=row_id, text=source)], ["text"], language
            )
        return out.text
    except Exception as e:  # noqa: BLE001 — serve English, never raise
        logger.error("[SYSTEM_COPY] localize %s → %s failed: %s", key, language, e)
        return source
