"""Unit tests for :func:`app.core.text.escape_angle_brackets` (SC-1).

The transform escapes ``<`` and ``>`` and nothing else, which is what makes it
idempotent — a property a following test pins so that anyone reaching for
``html.escape`` (which also escapes ``&``) breaks this file.
"""

from app.core.text import escape_angle_brackets


def test_escapes_angle_brackets():
    assert escape_angle_brackets("a<b>c") == "a&lt;b&gt;c"


def test_leaves_ampersand_alone():
    # html.escape would turn this into "a &amp; b" and destroy idempotence.
    assert escape_angle_brackets("a & b") == "a & b"
    assert "&amp;" not in escape_angle_brackets("a & b & c")


def test_leaves_square_brackets_alone():
    # The duplicate-booking guard scans [possible-duplicate:<id>] with a regex.
    assert escape_angle_brackets("[possible-duplicate:abc123]") == (
        "[possible-duplicate:abc123]"
    )


def test_idempotent_escaping_twice_equals_once():
    once = escape_angle_brackets("dinner <7pm & price >6")
    twice = escape_angle_brackets(once)
    assert twice == once
    # Concretely: the already-escaped entities are untouched, not re-escaped.
    assert once == "dinner &lt;7pm & price &gt;6"


def test_lossless_nothing_deleted():
    assert escape_angle_brackets("dinner <7pm") == "dinner &lt;7pm"


def test_empty_string():
    assert escape_angle_brackets("") == ""


def test_plain_text_unchanged():
    plain = "a normal sentence with no markup."
    assert escape_angle_brackets(plain) == plain
