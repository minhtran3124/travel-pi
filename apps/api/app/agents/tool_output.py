"""Pure helpers that label tool results as data, not instructions.

A retrieved document or a tool result arrives as unlabelled text in the same
conversation the assistant's own rules live in, so a hotel review containing
"ignore your previous instructions and …" is typographically indistinguishable
from an instruction. Wrapping every tool result in a labelled block — after
escaping its angle brackets — lets the model read it as data.

This module is *pure*: no langgraph import, no I/O. The hook in
``app.agents.subagents._base`` is the only caller of :func:`wrap_tool_output`;
the eval adapter is the only caller of :func:`strip_wrappers` (see the spec's
D7). Escaping is idempotent (:func:`app.core.text.escape_angle_brackets`);
wrapping is not, so the hook must run it exactly once per tool call.
"""

import re

from app.core.text import escape_angle_brackets

#: The tag name used for the wrapper block. Tests derive their expected strings
#: from these constants rather than hardcoding tag text, so a rename here does
#: not silently pass a whole test file.
TAG_NAME = "tool_output"

#: Template for the opening tag; ``{name}`` is filled with the *escaped* tool
#: name. ``OPEN_TAG_TEMPLATE.format(name=...)`` yields the literal opening tag.
OPEN_TAG_TEMPLATE = f'<{TAG_NAME} name="{{name}}">'

#: The literal closing tag.
CLOSE_TAG = f"</{TAG_NAME}>"

# Removal patterns for strip_wrappers. The opening tag carries a variable
# ``name`` attribute, so there is no fixed token to str.replace — hence a regex.
# Each pattern also swallows the single newline the wrapper added on that side,
# so strip_wrappers(wrap_tool_output(n, x)) == escape_angle_brackets(x) exactly,
# with no leading/trailing blank line. re.sub removes *every* occurrence, which
# a caller joining a transcript from many messages relies on.
_OPEN_RE = re.compile(re.escape(f"<{TAG_NAME} ") + r'name="[^"]*">\n')
_CLOSE_RE = re.compile("\n" + re.escape(CLOSE_TAG))


def wrap_tool_output(name: str, text: str) -> str:
    """Wrap ``text`` in a ``<tool_output>`` block, escaping angle brackets.

    Produces ``<tool_output name="{escaped name}">\\n{escaped text}\\n</tool_output>``.
    Both the ``name`` attribute and the body are escaped, so neither a hostile
    payload nor a hostile tool name can emit a literal ``<``/``>`` and forge a
    delimiter — after escaping, the only angle brackets in the result are the
    wrapper's own tags.

    :param name: The tool name (used as the block's ``name`` attribute).
    :param text: The tool result text to wrap.
    :return: The escaped, wrapped block.
    """
    escaped_name = escape_angle_brackets(name)
    escaped_text = escape_angle_brackets(text)
    return f"{OPEN_TAG_TEMPLATE.format(name=escaped_name)}\n{escaped_text}\n{CLOSE_TAG}"


def strip_wrappers(text: str) -> str:
    """Remove every ``<tool_output>`` wrapper, leaving the escaped content.

    A **regex** removal, not ``str.replace``: the opening tag carries a variable
    ``name`` attribute, so there is no fixed token. Each opening tag is removed
    together with the newline the wrapper added after it, and each closing tag
    with the newline before it, so ``strip_wrappers(wrap_tool_output(n, x))``
    equals ``escape_angle_brackets(x)`` byte-for-byte — no leading or trailing
    blank line. Every occurrence is removed, so a transcript joined from many
    wrapped messages comes back fully unwrapped.

    It does **not** unescape: re-importing a literal ``<`` would re-open tag
    forgery in the consumer (the eval judge's retrieval context).

    :param text: Text possibly containing one or more wrapper blocks.
    :return: ``text`` with all wrapper tags (and their added newlines) removed.
    """
    text = _OPEN_RE.sub("", text)
    text = _CLOSE_RE.sub("", text)
    return text
