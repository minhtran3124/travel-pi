#!/usr/bin/env python3
"""Pre-fill ``app/data/content_translations.<lang>.json`` for the seeded catalog.

Runs the same ``ContentTranslationService.localize`` the tools use, over every
seeded place and hotel (``description``), against the configured LLM, and writes the
resulting ``content_translations`` rows for ``--language`` to the checked-in JSON
so a fresh deployment never pays a runtime translation for seed data. Rows that
already exist (from an earlier run or a lazy tool-time fill) are reused, so
re-running only translates what is still missing.

Run as a module from ``apps/api/`` with a real provider key configured::

    python -m scripts.generate_translations --language vi

Runs against ``settings.database_url`` (respects ``DATABASE_URL`` / ``.env``);
the DB must be seeded (``make seed``). The JSON is data — hand-edit freely.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.agent_config_cache import reload_from_db
from app.core.config import get_settings
from app.core.languages import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.db import models
from app.db.engine import get_session_factory
from app.repositories.hotel_ref import HotelRepository
from app.repositories.place_ref import PlaceRepository
from app.services.content_translation_service import (
    ContentTranslationService,
    Translator,
)
from sqlalchemy import select

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"

#: entity_type -> (loader(session) -> list[BaseModel], fields)
_CATALOG = {
    "place": (lambda s: PlaceRepository(s).all(), ["description"]),
    "hotel": (lambda s: HotelRepository(s).all(), ["description"]),
}


def generate(
    session_factory,
    language: str,
    translator: Translator | None = None,
    batch: int = 20,
) -> list[dict]:
    """Localize the seeded catalog and return the rows for ``language``.

    :param session_factory: Callable returning a session (context manager).
    :param language: Target language code (never the default).
    :param translator: Optional translator override (tests); default = the LLM.
    :param batch: Entities per translator call.
    :return: ``[{"entity_type","entity_id","field","text"}]`` sorted by key.
    """
    with session_factory() as s:
        svc = ContentTranslationService(s, translator)
        for entity_type, (load, fields) in _CATALOG.items():
            items = load(s)
            for i in range(0, len(items), batch):
                svc.localize(entity_type, items[i : i + batch], fields, language)
        s.commit()
        rows = s.execute(
            select(
                models.ContentTranslation.entity_type,
                models.ContentTranslation.entity_id,
                models.ContentTranslation.field,
                models.ContentTranslation.text,
            )
            .where(models.ContentTranslation.language == language)
            .order_by(
                models.ContentTranslation.entity_type,
                models.ContentTranslation.entity_id,
                models.ContentTranslation.field,
            )
        ).all()
    return [
        {"entity_type": t, "entity_id": i, "field": f, "text": x} for t, i, f, x in rows
    ]


def write(rows: list[dict], language: str, data_dir: Path = DATA_DIR) -> Path:
    """Write ``rows`` to ``content_translations.<language>.json``.

    :return: The written path.
    """
    path = data_dir / f"content_translations.{language}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        required=True,
        choices=[c for c in SUPPORTED_LANGUAGES if c != DEFAULT_LANGUAGE],
    )
    args = parser.parse_args()
    factory = get_session_factory(get_settings().database_url)
    # Outside the app lifespan the per-agent config cache is empty and
    # get_agent_llm would fall back to the env model; load the DB rows first.
    reload_from_db(factory)
    rows = generate(factory, args.language)
    path = write(rows, args.language)
    print(f"wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
