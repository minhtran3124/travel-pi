"""``with_task_note`` — the per-turn specialist task, folded into the leading system message."""

from app.agents.constants import TASK_NOTE_PREAMBLE
from app.agents.state import with_task_note
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

BASE = SystemMessage(content="You are the planner.")


def test_unchanged_without_tasks():
    assert with_task_note(BASE, {}) is BASE
    assert with_task_note(BASE, {"tasks": []}) is BASE
    assert with_task_note(BASE, {"tasks": None}) is BASE


def test_unchanged_on_blank_query():
    assert with_task_note(BASE, {"tasks": [{"query": ""}]}) is BASE
    assert with_task_note(BASE, {"tasks": [{"query": "   "}]}) is BASE
    assert with_task_note(BASE, {"tasks": [{}]}) is BASE


def test_ignores_undeclared_task_key():
    # A compiled subgraph drops keys its schema does not declare, so a lone
    # ``task`` key must never be read — only the declared ``tasks`` list.
    assert with_task_note(BASE, {"task": {"query": "find hotels"}}) is BASE


def test_reads_first_task_only():
    out = with_task_note(
        BASE, {"tasks": [{"query": "find hotels"}, {"query": "second-task"}]}
    )

    assert out.content.endswith("find hotels")
    assert "second-task" not in out.content


def test_folds_note_into_base():
    out = with_task_note(BASE, {"tasks": [{"query": "book the Da Nang flight"}]})

    assert isinstance(out, SystemMessage)
    assert out.content.startswith(BASE.content)
    assert TASK_NOTE_PREAMBLE in out.content
    assert out.content.endswith(TASK_NOTE_PREAMBLE + "book the Da Nang flight")
    assert TASK_NOTE_PREAMBLE.endswith("\n\n")
    assert "The messages above" not in TASK_NOTE_PREAMBLE


def test_skips_when_query_equals_last_user_message():
    # Single-intent (or fallback) turn: the query IS the traveller's sentence,
    # already in the conversation — copying it into the system prompt adds nothing.
    sentence = "flights to Tokyo next week"
    for user_text, query in [
        (sentence, sentence),
        (f"  {sentence}\n", sentence),
        (sentence, f"  {sentence}  "),
    ]:
        state = {
            "messages": [HumanMessage(content=user_text)],
            "tasks": [{"query": query}],
        }
        assert with_task_note(BASE, state) is BASE


def test_compares_against_last_user_message_only():
    state = {
        "messages": [
            HumanMessage(content="find hotels"),
            AIMessage(content="Which city?"),
            HumanMessage(content="Da Nang please"),
        ],
        "tasks": [{"query": "find hotels"}],
    }
    out = with_task_note(BASE, state)
    assert out.content.endswith(TASK_NOTE_PREAMBLE + "find hotels")


def test_adds_note_when_query_differs_from_user_message():
    state = {
        "messages": [HumanMessage(content="flights to Tokyo and a visa question")],
        "tasks": [{"query": "find flights to Tokyo"}],
    }
    out = with_task_note(BASE, state)
    assert out is not BASE
    assert out.content.endswith(TASK_NOTE_PREAMBLE + "find flights to Tokyo")


def test_no_human_message_still_adds_note():
    state = {
        "messages": [AIMessage(content="find flights to Tokyo")],
        "tasks": [{"query": "find flights to Tokyo"}],
    }
    out = with_task_note(BASE, state)
    assert out.content.endswith(TASK_NOTE_PREAMBLE + "find flights to Tokyo")
