"""The traveller's view of a dossier file: no tool names, no ids.

The stored dossier keeps ``(search_flights)`` citations after every fact and the ids the
proposal is built from — the grader checks the citations and the main agent assembles
``/plan/proposal.json`` from the ids — so both stay in the file. They are noise to a
traveller, so every traveller-facing read goes through :func:`reader_view`: citation
parentheses and labelled ids are dropped, and so are lines that only list bare ids and
the trailing ``## Ids`` section. Markdown links pass through untouched: they are the
traveller-facing sources (the ``## Sources`` list), so an id inside a URL stays.
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
_LINK = re.compile(r"\[[^\]\n]*\]\([^()\s]+\)")
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


def _mask_links(line: str) -> tuple[str, list[str]]:
    links: list[str] = []

    def _keep(match: re.Match[str]) -> str:
        links.append(match.group(0))
        return f"\x00{len(links) - 1}\x00"

    return _LINK.sub(_keep, line), links


def _unmask_links(line: str, links: list[str]) -> str:
    for index, link in enumerate(links):
        line = line.replace(f"\x00{index}\x00", link)
    return line


def reader_view(text: str) -> str:
    """Return *text* as the traveller should read it."""
    lines: list[str] = []
    for line in _without_ids_section(text.split("\n")):
        # A markdown link is a source the traveller can open: its title and URL pass
        # through untouched even when the URL holds an id. Everything around it is
        # stripped as usual.
        line, links = _mask_links(line)
        line = _LABELLED_ID.sub("", line)
        # An id with no label around it is a line written only to list ids for the
        # proposal ("shortlist: `a`, `b` and `c`"); cutting it out mid-sentence
        # leaves "shortlist:,, and.", so the line goes.
        if _BARE_UUID.search(line):
            continue
        line = _CITATION.sub(_drop_citation, line)
        lines.append(_unmask_links(_tidy(line).rstrip(), links))
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip("\n")
    return f"{out}\n" if text.endswith("\n") else out
