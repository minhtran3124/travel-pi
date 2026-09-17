"""Language-keyed catalog text, one row per ``(entity_type, entity_id, field, language)``.

Only non-default languages get rows. Entities live in different tables, so ``entity_id``
is deliberately not a foreign key.
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
