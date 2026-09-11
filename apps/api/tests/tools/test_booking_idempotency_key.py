"""Tests for the turn-scoped idempotency key helper (gh-193, task 1.1).

The helper is pure and side-effect free: it derives a stable key from the
turn context (thread id + last HumanMessage id), the tool name, and the
model-visible args, ignoring injected/config plumbing. No DB fixture is
needed — these tests only call the helper.
"""

from app.tools._idempotency import INJECTED_ARG_NAMES, turn_idempotency_key
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

USER = "u_owner"
TOOL = "book_flight"
ARGS = {"flight_number": "VN123", "passengers": 2, "confirm": True}


def _config(thread_id="thread-1"):
    return {"configurable": {"thread_id": thread_id}}


def _messages(human_id="hm-1"):
    return [
        SystemMessage(content="system"),
        HumanMessage(content="book it", id=human_id),
        AIMessage(content="ok"),
    ]


def test_same_inputs_same_key():
    a = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    b = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    assert a is not None
    assert a == b


def test_key_is_sha256_hex_digest():
    key = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_different_thread_differs():
    a = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config("t-a"), messages=_messages()
    )
    b = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config("t-b"), messages=_messages()
    )
    assert a != b


def test_different_human_message_id_differs():
    a = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages("hm-a")
    )
    b = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages("hm-b")
    )
    assert a != b


def test_different_tool_name_differs():
    a = turn_idempotency_key(
        "book_flight", dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    b = turn_idempotency_key(
        "book_hotel", dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    assert a != b


def test_different_arg_differs():
    a = turn_idempotency_key(
        TOOL,
        {"flight_number": "VN123", "passengers": 2},
        user_id=USER,
        config=_config(),
        messages=_messages(),
    )
    b = turn_idempotency_key(
        TOOL,
        {"flight_number": "VN123", "passengers": 3},
        user_id=USER,
        config=_config(),
        messages=_messages(),
    )
    assert a != b


def test_injected_keys_ignored():
    without = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    with_injected = dict(ARGS)
    for name in INJECTED_ARG_NAMES:
        with_injected[name] = "should-be-dropped"
    withk = turn_idempotency_key(
        TOOL, with_injected, user_id=USER, config=_config(), messages=_messages()
    )
    assert without == withk


def test_no_thread_returns_none():
    assert (
        turn_idempotency_key(
            TOOL, dict(ARGS), user_id=USER, config=None, messages=_messages()
        )
        is None
    )
    assert (
        turn_idempotency_key(
            TOOL,
            dict(ARGS),
            user_id=USER,
            config={"configurable": {}},
            messages=_messages(),
        )
        is None
    )
    assert (
        turn_idempotency_key(
            TOOL,
            dict(ARGS),
            user_id=USER,
            config=_config(""),
            messages=_messages(),
        )
        is None
    )


def test_no_human_message_returns_none():
    assert (
        turn_idempotency_key(
            TOOL, dict(ARGS), user_id=USER, config=_config(), messages=None
        )
        is None
    )
    assert (
        turn_idempotency_key(
            TOOL,
            dict(ARGS),
            user_id=USER,
            config=_config(),
            messages=[SystemMessage(content="s"), AIMessage(content="a")],
        )
        is None
    )


def test_empty_human_message_id_returns_none():
    assert (
        turn_idempotency_key(
            TOOL,
            dict(ARGS),
            user_id=USER,
            config=_config(),
            messages=[HumanMessage(content="hi", id="")],
        )
        is None
    )


def test_trailing_system_message_does_not_change_key():
    """A revise note appended as a trailing SystemMessage after the last
    HumanMessage must not change the key — the key is turn-scoped to the last
    HumanMessage id, not the message tail."""
    base = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=_messages()
    )
    with_note = _messages() + [SystemMessage(content="revise: fix the phone")]
    revised = turn_idempotency_key(
        TOOL, dict(ARGS), user_id=USER, config=_config(), messages=with_note
    )
    assert base == revised
