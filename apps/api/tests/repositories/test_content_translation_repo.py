"""ContentTranslationRepo — get_many / upsert_many on a fresh SQLite DB."""

import pytest
from app.db import models  # noqa: F401 — registers models on Base
from app.db.base import Base
from app.repositories.content_translation import ContentTranslationRepo
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ct.db'}", future=True)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, future=True)
    engine.dispose()


def _row(
    entity_id="p1", field="description", language="vi", text="mô tả", source="llm"
):
    return {
        "entity_type": "place",
        "entity_id": entity_id,
        "field": field,
        "language": language,
        "text": text,
        "source": source,
    }


def test_get_many_returns_only_matching_rows(factory):
    repo = ContentTranslationRepo(factory)
    repo.upsert_many(
        [
            _row("p1"),
            _row("p2", text="khác"),
            _row("p1", field="name", text="tên"),
            _row("p1", language="en", text="ignored"),
        ]
    )

    got = repo.get_many("place", ["p1", "p2", "p9"], ["description"], "vi")

    assert got == {("p1", "description"): "mô tả", ("p2", "description"): "khác"}


def test_get_many_short_circuits_on_empty_inputs(factory):
    repo = ContentTranslationRepo(factory)
    assert repo.get_many("place", [], ["description"], "vi") == {}
    assert repo.get_many("place", ["p1"], [], "vi") == {}


def test_upsert_overwrites_by_unique_key(factory):
    repo = ContentTranslationRepo(factory)
    assert repo.upsert_many([_row(text="v1", source="llm")]) == 1
    assert repo.upsert_many([_row(text="v2", source="seed")]) == 1

    with factory() as s:
        rows = s.query(models.ContentTranslation).all()
    assert len(rows) == 1
    assert rows[0].text == "v2"
    assert rows[0].source == "seed"


def test_upsert_live_session_flushes_without_commit(factory):
    with factory() as s:
        repo = ContentTranslationRepo(s)
        repo.upsert_many([_row()])
        assert repo.get_many("place", ["p1"], ["description"], "vi") == {
            ("p1", "description"): "mô tả"
        }
        s.rollback()
    with factory() as s:
        assert s.query(models.ContentTranslation).count() == 0
