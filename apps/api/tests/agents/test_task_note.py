"""``task_note`` — the per-turn specialist steering note (specs/specialist-task-description)."""

from app.agents.constants import TASK_NOTE_PREAMBLE
from app.agents.state import task_note
from langchain_core.messages import HumanMessage, SystemMessage


def test_reads_first_task():
    note = task_note({"tasks": [{"query": "find hotels"}, {"query": "ignored"}]})

    assert note is not None
    assert note.content.endswith("find hotels")
    assert "ignored" not in note.content


def test_ignores_undeclared_task_key():
    # A compiled subgraph drops keys its schema does not declare, so a lone
    # ``task`` key must never be read — only the declared ``tasks`` list.
    assert task_note({"task": {"query": "find hotels"}}) is None


def test_none_without_tasks():
    assert task_note({}) is None
    assert task_note({"tasks": []}) is None
    assert task_note({"tasks": None}) is None


def test_none_on_blank_query():
    assert task_note({"tasks": [{"query": ""}]}) is None
    assert task_note({"tasks": [{"query": "   "}]}) is None
    assert task_note({"tasks": [{}]}) is None


def test_content_starts_with_preamble_and_ends_with_query():
    note = task_note({"tasks": [{"query": "book the Da Nang flight"}]})

    assert note is not None
    assert note.content.startswith(TASK_NOTE_PREAMBLE)
    assert note.content.endswith("book the Da Nang flight")
    assert TASK_NOTE_PREAMBLE.endswith("\n\n")


def test_is_system_message_not_human():
    note = task_note({"tasks": [{"query": "find hotels"}]})

    assert isinstance(note, SystemMessage)
    assert not isinstance(note, HumanMessage)
