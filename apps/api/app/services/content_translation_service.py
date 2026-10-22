"""Localize catalog entities to the conversation language (best-effort; never raises)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.clients.llm import get_agent_llm
from app.core.languages import DEFAULT_LANGUAGE, LANGUAGE_NAMES, normalize
from app.repositories.content_translation import ContentTranslationRepo

logger = logging.getLogger(__name__)

#: ``translator(texts, language) -> translated texts`` (same length and order).
Translator = Callable[[list[str], str], list[str]]

#: Reuses an existing node name — a new one seeds a NULL model and 403s in Docker.
TRANSLATOR_AGENT = "extract_memory"

_SYSTEM = (
    "You are a translator. Translate EACH text in the list into {language}. "
    "Keep proper nouns (place names, brands, cities, landmarks) unchanged. "
    "Return exactly one translation per input, in the same order, with no "
    "preamble or commentary."
)

M = TypeVar("M", bound=BaseModel)


class TranslationBatch(BaseModel):
    """Structured translator reply: one item per input text, same order."""

    items: list[str] = Field(..., description="Translations, one per input, in order.")


def llm_translator(
    texts: list[str], language: str, *, instructions: str | None = None
) -> list[str]:
    """Translate ``texts`` in one structured LLM call."""
    llm = get_agent_llm(TRANSLATOR_AGENT).with_structured_output(TranslationBatch)
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    system = _SYSTEM.format(language=LANGUAGE_NAMES[language])
    if instructions:
        system = f"{system} {instructions}"
    result = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=numbered),
        ]
    )
    items = result.items if isinstance(result, TranslationBatch) else None
    if items is None or len(items) != len(texts):
        raise ValueError(
            f"translator returned {0 if items is None else len(items)} items "
            f"for {len(texts)} inputs"
        )
    # Strip an echoed "N. " prefix matching the item's own index.
    return [
        item[len(f"{i + 1}. ") :] if item.startswith(f"{i + 1}. ") else item
        for i, item in enumerate(items)
    ]


class ContentTranslationService:
    """Overlay stored translations onto entities; fill misses once, in one batch."""

    def __init__(self, session: Session, translator: Translator | None = None) -> None:
        self._repo = ContentTranslationRepo(session)
        self._translator = translator or llm_translator

    def localize(
        self,
        entity_type: str,
        items: Sequence[M],
        fields: Sequence[str],
        language: str | None,
        *,
        fill_misses: bool = True,
    ) -> list[M]:
        """Return ``items`` with ``fields`` in ``language`` (default language is a no-op)."""
        lang = normalize(language)
        items = list(items)
        if lang == DEFAULT_LANGUAGE or not items or not fields:
            return items

        ids = [item.id for item in items]
        stored = self._repo.get_many(entity_type, ids, fields, lang)

        misses: list[tuple[str, str, str]] = []  # (entity_id, field, source_text)
        for item in items:
            for field in fields:
                if (item.id, field) in stored:
                    continue
                source = getattr(item, field, None)
                if isinstance(source, str) and source:
                    misses.append((item.id, field, source))

        if misses and fill_misses:
            stored = {**stored, **self._fill(entity_type, misses, lang)}

        return [
            item.model_copy(
                update={
                    field: stored[(item.id, field)]
                    for field in fields
                    if (item.id, field) in stored
                }
            )
            for item in items
        ]

    def _fill(
        self, entity_type: str, misses: list[tuple[str, str, str]], language: str
    ) -> dict[tuple[str, str], str]:
        """Translate every miss in one call and persist the result (best-effort)."""
        try:
            translated = self._translator([m[2] for m in misses], language)
        except Exception as e:  # noqa: BLE001 — keep source text, never raise
            logger.error(
                "[CONTENT_I18N] translate failed (%s, %d texts → %s): %s",
                entity_type,
                len(misses),
                language,
                e,
            )
            return {}
        if len(translated) != len(misses):
            logger.error(
                "[CONTENT_I18N] translator returned %d items for %d inputs; kept source",
                len(translated),
                len(misses),
            )
            return {}

        filled = {
            (eid, field): text
            for (eid, field, _), text in zip(misses, translated, strict=True)
        }
        try:
            self._repo.upsert_many(
                {
                    "entity_type": entity_type,
                    "entity_id": eid,
                    "field": field,
                    "language": language,
                    "text": text,
                    "source": "llm",
                }
                for (eid, field), text in filled.items()
            )
        except Exception as e:  # noqa: BLE001 — serve the translation anyway
            logger.error("[CONTENT_I18N] write-back failed: %s", e)
        logger.info(
            "[CONTENT_I18N] translated %d %s text(s) → %s",
            len(filled),
            entity_type,
            language,
        )
        return filled
