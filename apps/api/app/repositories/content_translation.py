"""Data-access for ``content_translations`` — one lookup, one upsert, no logic.

``get_many`` is the hot path (one ``IN`` query per panel, ≤ a handful of ids on
the unique index); ``upsert_many`` is the cold path that fills misses. Business
rules (which fields, batching, the translator) live in
``app.services.content_translation_service``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo


class ContentTranslationRepo(Repo):
    """Store of translated catalog text keyed by (entity_type, entity_id, field, language)."""

    def get_many(
        self,
        entity_type: str,
        entity_ids: Sequence[str],
        fields: Sequence[str],
        language: str,
    ) -> dict[tuple[str, str], str]:
        """Return stored text for the requested entities/fields in ``language``.

        :param entity_type: The catalog entity kind (``"place"``, ``"hotel"``).
        :param entity_ids: Entity ids to look up (empty → empty result, no query).
        :param fields: Field names to look up (empty → empty result, no query).
        :param language: The target language code.
        :return: ``{(entity_id, field): text}`` for every row found.
        """
        if not entity_ids or not fields:
            return {}
        stmt = select(
            models.ContentTranslation.entity_id,
            models.ContentTranslation.field,
            models.ContentTranslation.text,
        ).where(
            models.ContentTranslation.entity_type == entity_type,
            models.ContentTranslation.entity_id.in_(list(entity_ids)),
            models.ContentTranslation.field.in_(list(fields)),
            models.ContentTranslation.language == language,
        )
        with self._session() as s:
            return {(eid, field): text for eid, field, text in s.execute(stmt)}

    def upsert_many(self, rows: Iterable[dict]) -> int:
        """Insert or overwrite rows by their unique key.

        Each row: ``{"entity_type", "entity_id", "field", "language", "text", "source"}``.
        Existing rows get ``text``/``source`` overwritten (seed re-runs, re-translation).

        :param rows: The rows to write.
        :return: The number of rows written.
        """
        rows = list(rows)
        if not rows:
            return 0
        with self._session() as s:
            for row in rows:
                stmt = select(models.ContentTranslation).where(
                    models.ContentTranslation.entity_type == row["entity_type"],
                    models.ContentTranslation.entity_id == row["entity_id"],
                    models.ContentTranslation.field == row["field"],
                    models.ContentTranslation.language == row["language"],
                )
                existing = s.scalars(stmt).first()
                if existing is None:
                    s.add(models.ContentTranslation(**row))
                else:
                    existing.text = row["text"]
                    existing.source = row["source"]
            self._commit(s)
        return len(rows)
