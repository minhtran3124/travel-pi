"""system_reply: English is the single source; other languages are translated once, cached, and any failure serves English."""

from __future__ import annotations

import re
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.agents import copy as mod
from app.agents.constants import BOOKING_UPGRADE_MSG, NOT_SURE_MSG
from app.agents.context import resolve_agent_context
from app.agents.copy import SYSTEM_COPY, system_reply
from app.agents.supervisor import SupervisorIntent, make_supervisor
from app.clients.llm import FakeLLM
from app.db import models  # noqa: F401 — registers models on Base
from app.db.base import Base
from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class Spy:
    def __init__(self, fail: bool = False):
        self.calls: list[tuple[list[str], str]] = []
        self.fail = fail

    def __call__(self, texts, language):
        self.calls.append((list(texts), language))
        if self.fail:
            raise RuntimeError("boom")
        return [f"{language.upper()}:{t}" for t in texts]


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """Point ``system_reply`` at an isolated SQLite translation store."""
    engine = create_engine(f"sqlite:///{tmp_path / 'copy.db'}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)

    @contextmanager
    def _scope():
        s = factory()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    monkeypatch.setattr(mod, "session_scope", _scope)
    yield
    engine.dispose()


def test_every_key_has_non_empty_english_source():
    assert SYSTEM_COPY and all(v.strip() for v in SYSTEM_COPY.values())


def test_default_language_is_identity_no_session(monkeypatch):
    def boom():
        raise AssertionError("DB must not be opened for the default language")

    monkeypatch.setattr(mod, "session_scope", boom)
    assert system_reply("booking_upgrade", "en") == BOOKING_UPGRADE_MSG
    assert system_reply("booking_upgrade", None) == BOOKING_UPGRADE_MSG
    assert system_reply("booking_upgrade", "xx") == BOOKING_UPGRADE_MSG


def test_vi_is_translated_once_then_served_from_cache(scope):
    spy = Spy()
    first = system_reply("booking_upgrade", "vi", translator=spy)
    assert first == f"VI:{BOOKING_UPGRADE_MSG}"
    assert spy.calls == [([BOOKING_UPGRADE_MSG], "vi")]

    second = system_reply("booking_upgrade", "vi", translator=spy)
    assert second == first
    assert len(spy.calls) == 1


def test_default_translator_carries_the_assistant_persona(scope, monkeypatch):
    seen: list[dict] = []

    def fake_llm_translator(texts, language, **kw):
        seen.append(kw)
        return [f"VI:{t}" for t in texts]

    monkeypatch.setattr(
        mod,
        "_translate_copy",
        partial(fake_llm_translator, instructions=mod.TRANSLATOR_INSTRUCTIONS),
    )
    assert system_reply("unknown_intent", "vi").startswith("VI:")
    assert seen == [{"instructions": mod.TRANSLATOR_INSTRUCTIONS}]
    assert "Tin" in mod.TRANSLATOR_INSTRUCTIONS


def test_translator_failure_serves_english(scope):
    assert (
        system_reply("unknown_intent", "vi", translator=Spy(fail=True)) == NOT_SURE_MSG
    )


def test_no_session_serves_english(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(mod, "session_scope", boom)
    assert (
        system_reply("agent_error_fallback", "vi")
        == SYSTEM_COPY["agent_error_fallback"]
    )


def test_supervisor_tier_gate_replies_in_the_detected_language(monkeypatch):
    """A free user's Vietnamese booking request gets the upgrade notice in this turn's detected language, not English."""
    seen: list[tuple[str, str | None]] = []

    def fake_reply(key, language, **_):
        seen.append((key, language))
        return f"[{language}] {SYSTEM_COPY[key]}"

    monkeypatch.setattr("app.agents.supervisor.system_reply", fake_reply)
    supervisor = make_supervisor(
        FakeLLM(
            structured_responses=[
                SupervisorIntent(target_agent="booking", language="vi")
            ]
        )
    )
    cmd = supervisor(
        {"messages": [HumanMessage(content="book cho mình cái rẻ nhất đi")]},
        SimpleNamespace(context=resolve_agent_context(tier="free")),
    )
    assert seen == [("booking_upgrade", "vi")]
    assert cmd.update["messages"][0].content.startswith("[vi]")
    assert cmd.update["language"] == "vi"


def test_editing_the_english_source_invalidates_the_cached_translation(
    scope, monkeypatch
):
    spy = Spy()
    system_reply("booking_cancelled", "vi", translator=spy)
    monkeypatch.setitem(SYSTEM_COPY, "booking_cancelled", "Cancelled. Nothing booked.")
    assert (
        system_reply("booking_cancelled", "vi", translator=spy)
        == "VI:Cancelled. Nothing booked."
    )
    assert len(spy.calls) == 2  # edited source → fresh translation, not stale cache


def test_plan_node_reject_uses_the_conversation_language_and_approve_is_silent(
    monkeypatch,
):
    """Reject replies in the conversation language; approve emits no message since approval is state (plan_approved)."""
    from app.agents import nodes as nodes_mod

    seen: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        nodes_mod,
        "system_reply",
        lambda key, lang, **_: seen.append((key, lang)) or key,
    )
    monkeypatch.setattr(nodes_mod, "interrupt", lambda _payload: {"approved": False})
    cmd = nodes_mod.plan_node({"messages": [], "language": "vi"})
    assert seen == [("booking_cancelled", "vi")]
    assert cmd.update["messages"][0].content == "booking_cancelled"

    monkeypatch.setattr(nodes_mod, "interrupt", lambda _payload: {"approved": True})
    cmd = nodes_mod.plan_node({"messages": [], "language": "vi"})
    assert seen == [("booking_cancelled", "vi")]  # no copy call on approve
    assert "messages" not in cmd.update
    assert cmd.update["plan_approved"] is True
    assert cmd.goto == "booking"


def test_no_literal_user_facing_aimessage_outside_copy_helper():
    """Every code-authored reply must go through ``system_reply``; a literal would leak English to non-English users."""
    root = Path(__file__).resolve().parents[2] / "app"
    files = [
        *root.joinpath("agents").rglob("*.py"),
        *root.joinpath("streaming").rglob("*.py"),
        root / "routers" / "agent.py",
    ]
    pattern = re.compile(r"""AIMessage\(\s*content=(?:f?["']|[A-Z_]+_MSG\b)""")
    offenders = [str(f) for f in files if pattern.search(f.read_text())]
    assert offenders == [], offenders
