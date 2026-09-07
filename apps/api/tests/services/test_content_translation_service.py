"""ContentTranslationService.localize — overlay, batched miss-fill, write-back."""

import pytest
from app.clients.llm import FakeLLM
from app.db import models  # noqa: F401 — registers models on Base
from app.db.base import Base
from app.services import content_translation_service as mod
from app.services.content_translation_service import (
    ContentTranslationService,
    TranslationBatch,
)
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class Thing(BaseModel):
    id: str
    name: str
    description: str


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'svc.db'}", future=True)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, future=True)
    engine.dispose()


class Spy:
    def __init__(self, fail=False, short=False):
        self.calls: list[tuple[list[str], str]] = []
        self.fail = fail
        self.short = short

    def __call__(self, texts, language):
        self.calls.append((list(texts), language))
        if self.fail:
            raise RuntimeError("boom")
        out = [f"VI:{t}" for t in texts]
        return out[:-1] if self.short else out


ITEMS = [
    Thing(id="a", name="A", description="cozy cafe"),
    Thing(id="b", name="B", description="old temple"),
]


def _svc(s, spy):
    return ContentTranslationService(s, spy)


def test_default_language_is_identity_no_query_no_llm(factory):
    spy = Spy()
    with factory() as s:
        out = _svc(s, spy).localize("place", ITEMS, ["description"], "en")
        assert _svc(s, spy).localize("place", ITEMS, ["description"], None) == ITEMS
    assert out == ITEMS
    assert out[0] is ITEMS[0]
    assert spy.calls == []


def test_misses_are_translated_in_one_batch_and_written_back(factory):
    spy = Spy()
    with factory() as s:
        out = _svc(s, spy).localize("place", ITEMS, ["description"], "vi")
        s.commit()

    assert [t.description for t in out] == ["VI:cozy cafe", "VI:old temple"]
    assert [t.name for t in out] == ["A", "B"]
    assert spy.calls == [(["cozy cafe", "old temple"], "vi")]
    with factory() as s:
        rows = (
            s.query(models.ContentTranslation)
            .order_by(models.ContentTranslation.entity_id)
            .all()
        )
    assert [
        (r.entity_type, r.entity_id, r.field, r.language, r.text, r.source)
        for r in rows
    ] == [
        ("place", "a", "description", "vi", "VI:cozy cafe", "llm"),
        ("place", "b", "description", "vi", "VI:old temple", "llm"),
    ]


def test_second_call_hits_store_and_makes_zero_llm_calls(factory):
    spy = Spy()
    with factory() as s:
        _svc(s, spy).localize("place", ITEMS, ["description"], "vi")
        s.commit()
    with factory() as s:
        out = _svc(s, spy).localize("place", ITEMS, ["description"], "vi")
    assert len(spy.calls) == 1
    assert [t.description for t in out] == ["VI:cozy cafe", "VI:old temple"]


def test_partial_hit_translates_only_the_missing_rows(factory):
    spy = Spy()
    with factory() as s:
        _svc(s, spy).localize("place", ITEMS[:1], ["description"], "vi")
        s.commit()
    with factory() as s:
        out = _svc(s, spy).localize("place", ITEMS, ["description"], "vi")
    assert spy.calls[-1] == (["old temple"], "vi")
    assert [t.description for t in out] == ["VI:cozy cafe", "VI:old temple"]


def test_translator_failure_keeps_source_text_and_writes_nothing(factory):
    spy = Spy(fail=True)
    with factory() as s:
        out = _svc(s, spy).localize("place", ITEMS, ["description"], "vi")
        s.commit()
    assert [t.description for t in out] == ["cozy cafe", "old temple"]
    with factory() as s:
        assert s.query(models.ContentTranslation).count() == 0


def test_count_mismatch_keeps_source_text(factory):
    spy = Spy(short=True)
    with factory() as s:
        out = _svc(s, spy).localize("place", ITEMS, ["description"], "vi")
    assert [t.description for t in out] == ["cozy cafe", "old temple"]


def test_default_translator_uses_structured_fake_llm(factory, monkeypatch):
    fake = FakeLLM(
        structured_responses=[TranslationBatch(items=["quán cà phê", "đền cổ"])]
    )
    monkeypatch.setattr(mod, "get_agent_llm", lambda name: fake)
    with factory() as s:
        out = ContentTranslationService(s).localize(
            "place", ITEMS, ["description"], "vi"
        )
    assert [t.description for t in out] == ["quán cà phê", "đền cổ"]


def test_default_translator_rejects_wrong_count(factory, monkeypatch):
    fake = FakeLLM(structured_responses=[TranslationBatch(items=["only one"])])
    monkeypatch.setattr(mod, "get_agent_llm", lambda name: fake)
    with factory() as s:
        out = ContentTranslationService(s).localize(
            "place", ITEMS, ["description"], "vi"
        )
    assert [t.description for t in out] == ["cozy cafe", "old temple"]
