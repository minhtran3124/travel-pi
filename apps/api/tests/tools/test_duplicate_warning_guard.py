"""Tests for the id-aware duplicate-warning turn guard (gh-200, task 1.2).

Pure, no DB — same shape as ``test_booking_idempotency_key.py``. The marker
now embeds the existing booking's id so an ``allow_duplicate`` override can be
refused only for the booking that was actually flagged this turn, while a bare
legacy ``[possible-duplicate]`` marker fails safe to the wildcard (refuse every
same-tool override that turn).
"""

from app.exceptions import (
    DUPLICATE_WARNING_MARKER,
    DUPLICATE_WARNING_MARKER_RE,
    DuplicateBookingError,
    duplicate_warning_marker,
)
from app.schemas.booking import Booking
from app.tools._idempotency import (
    DUPLICATE_WARNED_ANY,
    duplicate_override_refused,
    duplicate_warned_ids_this_turn,
    duplicate_warned_this_turn,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

BID = "11111111-1111-5111-8111-111111111111"
TOOL = "book_flight"


def _booking(bid: str = BID) -> Booking:
    return Booking.model_construct(id=bid)


def _error_tool_message(marker: str, *, name: str = TOOL, status: str = "error"):
    return ToolMessage(
        name=name,
        status=status,
        tool_call_id="c1",
        content=f"Tool call failed: a matching booking exists. {marker}",
    )


# --- SC-3: id-bearing marker (test names contain "marker") -------------------


def test_marker_appends_existing_id():
    b = _booking()
    err = DuplicateBookingError(existing=b)
    assert err.detail.endswith(f"[possible-duplicate:{b.id}]")


def test_marker_regex_extracts_id_and_none_for_legacy():
    b = _booking()
    detail = DuplicateBookingError(existing=b).detail
    assert DUPLICATE_WARNING_MARKER_RE.search(detail).group(1) == b.id
    assert DUPLICATE_WARNING_MARKER_RE.search("x [possible-duplicate]").group(1) is None
    assert DUPLICATE_WARNING_MARKER_RE.search("no tag") is None


def test_marker_not_double_tagged():
    b = _booking()
    tagged = f"already {duplicate_warning_marker('abc')}"
    assert DuplicateBookingError(tagged, existing=b).detail == tagged
    legacy = f"already {DUPLICATE_WARNING_MARKER}"
    assert DuplicateBookingError(legacy, existing=b).detail == legacy


# --- SC-4: id-aware turn guard (test names must NOT contain "marker") --------


def _human_then(*messages):
    return [HumanMessage(content="book it", id="hm-1"), *messages]


def test_guard_no_messages_empty():
    assert duplicate_warned_ids_this_turn(TOOL, None) == frozenset()
    assert duplicate_warned_ids_this_turn(TOOL, []) == frozenset()


def test_guard_warning_before_last_human_ignored():
    messages = [
        _error_tool_message(duplicate_warning_marker(BID)),
        HumanMessage(content="ok book again", id="hm-2"),
        AIMessage(content="sure"),
    ]
    assert duplicate_warned_ids_this_turn(TOOL, messages) == frozenset()


def test_guard_returns_existing_id():
    messages = _human_then(_error_tool_message(duplicate_warning_marker(BID)))
    assert duplicate_warned_ids_this_turn(TOOL, messages) == frozenset({BID})


def test_guard_legacy_bare_tag_returns_wildcard():
    messages = _human_then(_error_tool_message(DUPLICATE_WARNING_MARKER))
    assert duplicate_warned_ids_this_turn(TOOL, messages) == frozenset(
        {DUPLICATE_WARNED_ANY}
    )


def test_guard_ignores_other_tool_and_success_status():
    messages = _human_then(
        _error_tool_message(duplicate_warning_marker(BID), name="book_hotel"),
        _error_tool_message(duplicate_warning_marker(BID), status="success"),
    )
    assert duplicate_warned_ids_this_turn(TOOL, messages) == frozenset()


def test_guard_list_content_parts():
    marker = duplicate_warning_marker(BID)
    messages = _human_then(
        ToolMessage(
            name=TOOL,
            status="error",
            tool_call_id="c1",
            content=[{"type": "text", "text": f"Tool call failed. {marker}"}],
        )
    )
    assert duplicate_warned_ids_this_turn(TOOL, messages) == frozenset({BID})


def test_override_refused_semantics():
    assert duplicate_override_refused("a", frozenset({"a"})) is True
    assert duplicate_override_refused("b", frozenset({"a"})) is False
    assert duplicate_override_refused("b", frozenset({"*"})) is True
    assert duplicate_override_refused("b", frozenset()) is False


def test_bool_wrapper_matches_id_set():
    empty = None
    id_bearing = _human_then(_error_tool_message(duplicate_warning_marker(BID)))
    other = _human_then(
        _error_tool_message(duplicate_warning_marker(BID), name="book_hotel")
    )
    for messages in (empty, id_bearing, other):
        assert duplicate_warned_this_turn(TOOL, messages) == bool(
            duplicate_warned_ids_this_turn(TOOL, messages)
        )
