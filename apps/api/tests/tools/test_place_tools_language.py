"""search_places localizes place descriptions at tool time (specs/catalog-content-i18n)."""

import json

import pytest
from app.db import models
from app.db.engine import get_session_factory
from app.services import content_translation_service as mod
from app.tools.place_tools import search_places
from tests.tools.conftest import (
    agent_db,  # noqa: F401 — fixture not visible cross-package
)


@pytest.fixture(autouse=True)
def _no_seeded_translations(agent_db):  # noqa: F811
    """Start from an empty store: seed_all pre-fills content_translations from
    the checked-in vi file, which would hide the miss path these tests cover."""
    with get_session_factory(agent_db)() as s:
        s.query(models.ContentTranslation).delete()
        s.commit()


def _call(args: dict):
    return search_places.invoke(
        {"type": "tool_call", "id": "t1", "name": search_places.name, "args": args}
    )


class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, texts, language):
        self.calls.append((list(texts), language))
        return [f"VI:{t}" for t in texts]


def test_language_is_injected_not_model_facing():
    assert "language" not in search_places.args
    assert "language" in search_places.args_schema.model_fields


def test_vi_localizes_panel_descriptions_once(agent_db, monkeypatch):  # noqa: F811
    spy = Spy()
    monkeypatch.setattr(mod, "llm_translator", spy)

    first = _call({"city": "Da Nang", "category": "restaurant", "language": "vi"})
    places = first.artifact["data"]["places"]
    assert places and all(p["description"].startswith("VI:") for p in places)
    assert len(spy.calls) == 1
    assert spy.calls[0][1] == "vi"
    assert len(spy.calls[0][0]) == len(places)

    second = _call({"city": "Da Nang", "category": "restaurant", "language": "vi"})
    assert len(spy.calls) == 1  # served from content_translations, no LLM call
    assert second.artifact == first.artifact


def test_no_language_is_unchanged_and_no_llm(agent_db, monkeypatch):  # noqa: F811
    spy = Spy()
    monkeypatch.setattr(mod, "llm_translator", spy)

    out = _call({"city": "Da Nang", "category": "restaurant"})
    places = out.artifact["data"]["places"]
    assert places and not any(p["description"].startswith("VI:") for p in places)
    assert spy.calls == []
    assert "language" not in json.dumps(out.artifact)


def test_translator_failure_keeps_english(agent_db, monkeypatch):  # noqa: F811
    def boom(texts, language):
        raise RuntimeError("no llm")

    monkeypatch.setattr(mod, "llm_translator", boom)
    out = _call({"city": "Da Nang", "category": "restaurant", "language": "vi"})
    places = out.artifact["data"]["places"]
    assert places and not any(p["description"].startswith("VI:") for p in places)
