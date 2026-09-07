"""Language-keyed catalog text (specs/catalog-content-i18n).

One row per ``(entity_type, entity_id, field, language)``: the translated
``text`` of a free-form catalog field (e.g. a place's ``description``). The
source language (``app.core.languages.DEFAULT_LANGUAGE``) stays on the entity
row itself; only other languages get rows here. ``source`` records whether the
text came from the checked-in seed file or was filled lazily by the translator
LLM on a cache miss. Entities live in different tables, so ``entity_id`` is
deliberately not a foreign key.
"""

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class ContentTranslation(UUIDBase):
    __tablename__ = "content_translations"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "field",
            "language",
            name="uq_content_translations_key",
        ),
        Index("ix_content_translations_type_language", "entity_type", "language"),
    )

    entity_type: Mapped[str] = mapped_column(String, nullable=False)  # place | hotel
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)  # e.g. description
    language: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # seed | llm
