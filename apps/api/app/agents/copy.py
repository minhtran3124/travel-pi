"""Code-authored agent replies, translated once and cached; English on any failure."""

from __future__ import annotations

import hashlib
import logging
from functools import partial

from pydantic import BaseModel

from app.agents.constants import (
    AGENT_ERROR_FALLBACK_MSG,
    ASSISTANT_NAME,
    BOOKING_UPGRADE_MSG,
    NOT_SURE_MSG,
    PLAN_CANCELLED_MSG,
    RESEARCH_COMPLETED_MSG,
    RESEARCH_IN_PROGRESS_MSG,
    RESEARCH_LIMIT_REACHED_MSG,
    RESEARCH_NEEDS_TRIP_MSG,
    RESEARCH_STARTED_MSG,
    RESEARCH_UNAVAILABLE_MSG,
)
from app.core.languages import DEFAULT_LANGUAGE, normalize
from app.services.content_translation_service import (
    ContentTranslationService,
    Translator,
    llm_translator,
)
from app.tools._base import session_scope

logger = logging.getLogger(__name__)

#: Translation-store entity kind for system copy (rows keyed by copy key).
ENTITY_TYPE = "system_copy"

#: Stable key → English source text; never add a per-language variant.
SYSTEM_COPY: dict[str, str] = {
    "booking_upgrade": BOOKING_UPGRADE_MSG,
    "unknown_intent": NOT_SURE_MSG,
    "booking_cancelled": PLAN_CANCELLED_MSG,
    "agent_error_fallback": AGENT_ERROR_FALLBACK_MSG,
    "research_completed": RESEARCH_COMPLETED_MSG,
    "research_in_progress": RESEARCH_IN_PROGRESS_MSG,
    "research_limit_reached": RESEARCH_LIMIT_REACHED_MSG,
    "research_needs_trip": RESEARCH_NEEDS_TRIP_MSG,
    "research_started": RESEARCH_STARTED_MSG,
    "research_unavailable": RESEARCH_UNAVAILABLE_MSG,
}


#: Persona guidance: the assistant refers to itself by name, not "I", in every language.
TRANSLATOR_INSTRUCTIONS = (
    f"These texts are spoken by a travel assistant named {ASSISTANT_NAME}. "
    f"Where the text says 'I'/'my', refer to the assistant by name "
    f"('{ASSISTANT_NAME}') the way a friendly assistant would in the target "
    "language, instead of a first-person pronoun. Keep the name unchanged."
)

#: Default translator for system copy: the shared LLM translator + persona note.
_translate_copy: Translator = partial(
    llm_translator, instructions=TRANSLATOR_INSTRUCTIONS
)


class _Copy(BaseModel):
    id: str
    text: str


def system_reply(
    key: str, language: str | None, *, translator: Translator | None = None
) -> str:
    """Return the system copy for ``key`` in ``language``, English source on any failure."""
    source = SYSTEM_COPY[key]
    if normalize(language) == DEFAULT_LANGUAGE:
        return source
    # Row keyed by key + digest of the source, so editing a constant invalidates
    # its cached translations instead of serving a stale one.
    row_id = f"{key}:{hashlib.sha1(source.encode()).hexdigest()[:10]}"
    try:
        with session_scope() as s:
            [out] = ContentTranslationService(
                s, translator or _translate_copy
            ).localize(ENTITY_TYPE, [_Copy(id=row_id, text=source)], ["text"], language)
        return out.text
    except Exception as e:  # noqa: BLE001 — serve English, never raise
        logger.error("[SYSTEM_COPY] localize %s → %s failed: %s", key, language, e)
        return source
