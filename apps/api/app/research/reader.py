"""The traveller's view of a dossier file: no tool names, no ids.

The stored dossier keeps ``(search_flights)`` citations after every fact and the ids the
proposal is built from — the grader checks the citations and the main agent assembles
``/plan/proposal.json`` from the ids — so both stay in the file. They are noise to a
traveller, so every traveller-facing read goes through :func:`reader_view`: citation
parentheses and labelled ids are dropped, and so are lines that only list bare ids and
the trailing ``## Ids`` section. A ``## Sources`` section is left byte-for-byte: its
links are the traveller-facing evidence, so ids, uuids and citations inside it stay.
"""

from __future__ import annotations

import re
from functools import cache

#: Tokens besides tool names that the agent uses as a source in a citation.
_SOURCE_WORDS = frozenset({"memory", "user prompt", "user request", "trip summary"})
#: Deep-agent built-ins the model may also cite.
_BUILTIN_TOOLS = frozenset(
    {"read_file", "write_file", "edit_file", "task", "validate_proposal"}
)

_CITATION = re.compile(r"[ \t]*\(([^()\n]*)\)")
_LABELLED_ID = re.compile(
    r"[ \t]*[—,;-]?[ \t]*\b(?:place|hotel|offer|flight)[ _]id\b[ \t]*[:=]?[ \t]*"
    r"`?[A-Za-z0-9_-]{6,}`?",
    re.IGNORECASE,
)
_BARE_UUID = re.compile(
    r"[ \t]*`?\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b`?",
    re.IGNORECASE,
)
_IDS_HEADING = re.compile(r"^##[ \t]+Ids[ \t]*$", re.IGNORECASE)
_SOURCES_HEADING = re.compile(r"^##[ \t]+Sources[ \t]*$", re.IGNORECASE)
_SECTION_HEADING = re.compile(r"^#{1,2}[ \t]")


@cache
def _sources() -> frozenset[str]:
    from app.tools.registry import ALL_TOOLS

    return frozenset(t.name for t in ALL_TOOLS) | _BUILTIN_TOOLS | _SOURCE_WORDS


def _drop_citation(match: re.Match[str]) -> str:
    parts = [p.strip().strip("`").lower() for p in re.split(r"[,;/]", match.group(1))]
    if parts and all(parts) and all(p in _sources() for p in parts):
        return ""
    return match.group(0)


def _without_ids_section(lines: list[str]) -> list[str]:
    kept: list[str] = []
    skipping = False
    for line in lines:
        if _IDS_HEADING.match(line):
            skipping = True
            continue
        if skipping and _SECTION_HEADING.match(line):
            skipping = False
        if not skipping:
            kept.append(line)
    return kept


def _tidy(line: str) -> str:
    line = re.sub(r"(?<=\S)[ \t]{2,}", " ", line)
    line = re.sub(r"[ \t]+([.,;:!?])", r"\1", line)
    return re.sub(r"[,;]+(?=[.!?]|$)", "", line)


def _close_block(block: list[str], lines: list[str]) -> None:
    # Trailing blank lines go back to normal processing so the blank-run collapse
    # still applies between the last source link and the next section.
    while len(block) > 1 and not block[-1].strip():
        block.pop()
        lines.append("")


def reader_view(text: str) -> str:
    """Return *text* as the traveller should read it."""
    lines: list[str] = []
    sources: list[list[str]] = []
    block: list[str] | None = None
    for line in _without_ids_section(text.split("\n")):
        if block is not None and _SECTION_HEADING.match(line):
            _close_block(block, lines)
            block = None
        if _SOURCES_HEADING.match(line):
            block = [line]
            sources.append(block)
            lines.append(f"\x00SOURCES{len(sources) - 1}\x00")
            continue
        if block is not None:
            # Verbatim: the ``## Sources`` links are the traveller-facing evidence.
            block.append(line)
            continue
        line = _LABELLED_ID.sub("", line)
        # An id with no label around it is a line written only to list ids for the
        # proposal ("shortlist: `a`, `b` and `c`"); cutting it out mid-sentence
        # leaves "shortlist:,, and.", so the line goes.
        if _BARE_UUID.search(line):
            continue
        line = _CITATION.sub(_drop_citation, line)
        lines.append(_tidy(line).rstrip())
    if block is not None:
        _close_block(block, lines)
    # Collapse blank runs before restoring the sections, so the collapse can never
    # reach the verbatim ``## Sources`` lines (their sentinel breaks every run).
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    for index, section in enumerate(sources):
        out = out.replace(f"\x00SOURCES{index}\x00", "\n".join(section))
    out = out.rstrip("\n")
    return f"{out}\n" if text.endswith("\n") else out
