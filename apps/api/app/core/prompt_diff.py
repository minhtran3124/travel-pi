"""Line-level diff helper for comparing two prompt versions.

Wraps the stdlib ``difflib.SequenceMatcher`` to produce a unified diff plus a
side-by-side (left/right) alignment, so the dashboard can render either view
without recomputing anything. No external dependency, no logging — pure
function over two strings.
"""

import difflib
from dataclasses import dataclass


@dataclass
class DiffRow:
    """One rendered line in a diff view.

    :param tag: One of "context" (unchanged), "add", or "del".
    :param old_no: 1-based line number in ``old``, or ``None`` if the line
        doesn't exist on that side (e.g. an added line).
    :param new_no: 1-based line number in ``new``, or ``None`` if the line
        doesn't exist on that side (e.g. a deleted line).
    :param text: The line's content (no trailing newline).
    """

    tag: str
    old_no: int | None
    new_no: int | None
    text: str


def build_line_diff(old: str, new: str) -> dict:
    """Compute a unified and side-by-side line diff between ``old`` and ``new``.

    :param old: The original text.
    :param new: The new text.
    :return: A dict with three keys: ``"unified"`` (list[DiffRow] in document
        order), and ``"left"`` / ``"right"`` (list[DiffRow | None], aligned
        so ``left[i]`` and ``right[i]`` are the same row index in a
        side-by-side view — a ``None`` is padding where one side has no
        corresponding line).
    """
    a = old.splitlines()
    b = new.splitlines()

    unified: list[DiffRow] = []
    left: list[DiffRow | None] = []
    right: list[DiffRow | None] = []

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            for offset, line in enumerate(a[i1:i2]):
                row = DiffRow("context", i1 + offset + 1, j1 + offset + 1, line)
                unified.append(row)
                left.append(row)
                right.append(row)
        elif tag == "delete":
            for offset, line in enumerate(a[i1:i2]):
                row = DiffRow("del", i1 + offset + 1, None, line)
                unified.append(row)
                left.append(row)
                right.append(None)
        elif tag == "insert":
            for offset, line in enumerate(b[j1:j2]):
                row = DiffRow("add", None, j1 + offset + 1, line)
                unified.append(row)
                left.append(None)
                right.append(row)
        elif tag == "replace":
            del_rows = [
                DiffRow("del", i1 + offset + 1, None, line)
                for offset, line in enumerate(a[i1:i2])
            ]
            add_rows = [
                DiffRow("add", None, j1 + offset + 1, line)
                for offset, line in enumerate(b[j1:j2])
            ]
            unified.extend(del_rows)
            unified.extend(add_rows)
            for k in range(max(len(del_rows), len(add_rows))):
                left.append(del_rows[k] if k < len(del_rows) else None)
                right.append(add_rows[k] if k < len(add_rows) else None)

    return {"unified": unified, "left": left, "right": right}
