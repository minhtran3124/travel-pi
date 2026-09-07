"""search_hotels / browse_hotels localize hotel descriptions at tool time."""

import pytest
from app.db import models
from app.db.engine import get_session_factory
from app.services import content_translation_service as mod
from app.tools.hotel_tools import browse_hotels, search_hotels
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


SEARCH = {
    "city": "Da Nang",
    "check_in": "2027-04-10",
    "check_out": "2027-04-12",
    "rooms": 1,
    "adults": 2,
    "children": 0,
}


def _call(tool, args: dict):
    return tool.invoke(
        {"type": "tool_call", "id": "t1", "name": tool.name, "args": args}
    )


class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, texts, language):
        self.calls.append((list(texts), language))
        return [f"VI:{t}" for t in texts]


def test_language_is_injected_not_model_facing():
    for tool in (search_hotels, browse_hotels):
        assert "language" not in tool.args
        assert "language" in tool.args_schema.model_fields


def test_browse_vi_localizes_descriptions_once(agent_db, monkeypatch):  # noqa: F811
    spy = Spy()
    monkeypatch.setattr(mod, "llm_translator", spy)
    first = _call(browse_hotels, {"city": "Da Nang", "language": "vi"})
    hotels = first.artifact["data"]["hotels"]
    assert hotels and all(h["description"].startswith("VI:") for h in hotels)
    assert len(spy.calls) == 1 and spy.calls[0][1] == "vi"
    second = _call(browse_hotels, {"city": "Da Nang", "language": "vi"})
    assert len(spy.calls) == 1
    assert second.artifact == first.artifact


def test_search_vi_localizes_and_keeps_ranking_summary(agent_db, monkeypatch):  # noqa: F811
    spy = Spy()
    monkeypatch.setattr(mod, "llm_translator", spy)
    out = _call(search_hotels, {**SEARCH, "language": "vi"})
    hotels = out.artifact["data"]["hotels"]
    assert hotels and all(h["description"].startswith("VI:") for h in hotels)
    assert "Hotels panel" in out.content  # summary text untouched


def test_no_language_is_unchanged_and_no_llm(agent_db, monkeypatch):  # noqa: F811
    spy = Spy()
    monkeypatch.setattr(mod, "llm_translator", spy)
    out = _call(browse_hotels, {"city": "Da Nang"})
    hotels = out.artifact["data"]["hotels"]
    assert hotels and not any(h["description"].startswith("VI:") for h in hotels)
    assert spy.calls == []
