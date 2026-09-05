"""Seed pre-fill of content_translations + the one-off generator script."""

import json

from app.db import models
from app.db import seed as seed_mod
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from scripts.generate_translations import generate, write
from sqlalchemy import func, select


def _fresh(tmp_path):
    url = f"sqlite:///{tmp_path / 'seed.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)


def _count(sf):
    with sf() as s:
        return s.scalar(select(func.count()).select_from(models.ContentTranslation))


def test_seed_loads_checked_in_translations_idempotently(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "content_translations.vi.json").write_text(
        json.dumps(
            [
                {
                    "entity_type": "place",
                    "entity_id": "p1",
                    "field": "description",
                    "text": "một",
                },
                {
                    "entity_type": "hotel",
                    "entity_id": "h1",
                    "field": "description",
                    "text": "hai",
                },
            ]
        )
    )
    monkeypatch.setattr(seed_mod, "_TRANSLATIONS_DIR", data_dir)
    sf = _fresh(tmp_path)

    seed_all(sf)
    assert _count(sf) == 2
    seed_all(sf)
    assert _count(sf) == 2
    with sf() as s:
        row = s.scalars(
            select(models.ContentTranslation).where(
                models.ContentTranslation.entity_id == "p1"
            )
        ).one()
    assert (row.language, row.text, row.source) == ("vi", "một", "seed")


def test_seed_without_translation_files_seeds_nothing(tmp_path, monkeypatch):
    empty = tmp_path / "nodata"
    empty.mkdir()
    monkeypatch.setattr(seed_mod, "_TRANSLATIONS_DIR", empty)
    sf = _fresh(tmp_path)
    seed_all(sf)
    assert _count(sf) == 0


def test_generator_writes_rows_for_every_seeded_place_and_hotel(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_mod, "_TRANSLATIONS_DIR", tmp_path)  # no pre-fill
    sf = _fresh(tmp_path)
    seed_all(sf)
    calls = []

    def fake(texts, language):
        calls.append(len(texts))
        return [f"VI:{t}" for t in texts]

    rows = generate(sf, "vi", translator=fake, batch=50)
    with sf() as s:
        n_places = s.scalar(select(func.count()).select_from(models.Place))
        n_hotels = s.scalar(select(func.count()).select_from(models.Hotel))
    n_total = n_places + n_hotels

    assert len(rows) == n_total
    assert {r["entity_type"] for r in rows} == {"place", "hotel"}
    assert all(r["field"] == "description" for r in rows)
    assert all(r["text"].startswith("VI:") for r in rows)
    assert rows == sorted(rows, key=lambda r: (r["entity_type"], r["entity_id"]))
    assert sum(calls) == n_total
    assert len(calls) == -(-n_places // 50) + -(-n_hotels // 50)

    out = tmp_path / "out"
    out.mkdir()
    path = write(rows, "vi", out)
    assert json.loads(path.read_text()) == rows

    # Round trip: the written file seeds back into a fresh DB, and a re-run of
    # the generator translates nothing (every row is already stored).
    monkeypatch.setattr(seed_mod, "_TRANSLATIONS_DIR", out)
    (tmp_path / "second").mkdir()
    sf2 = _fresh(tmp_path / "second")
    seed_all(sf2)
    assert _count(sf2) == n_total
    calls.clear()
    assert generate(sf2, "vi", translator=fake) == rows
    assert calls == []
