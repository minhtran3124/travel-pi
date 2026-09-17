"""Data-access for ``content_translations`` — one lookup, one upsert; business rules live in content_translation_service."""

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
        """Return stored text for the requested entities/fields in ``language`` (empty ids/fields → empty result, no query)."""
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
        """Insert or overwrite rows by their unique key; existing rows get ``text``/``source`` overwritten."""
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
