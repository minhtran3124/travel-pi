---
name: dossier-format
description: Canonical file layout, heading conventions, and citation rule for the trip-research dossier. Activate at the start of every research turn and before writing any file under /research or /plan — it fixes exactly which files exist, where each dimension's findings belong, how headings are structured, and the rule that every factual claim must name the tool that produced it. Read it whenever you are about to create, edit, or review a dossier file so the layout stays consistent across turns and across subagents.
---

# Skill: dossier-format

The dossier is the deliverable. It is a set of Markdown files plus one JSON proposal,
stored under `/research/` and `/plan/`. This skill fixes the layout so every turn and
every subagent writes to the same place in the same shape.

## File layout (exact paths)

Write only to these paths. Never invent new top-level files.

| Path | Owner | Contents |
|---|---|---|
| `/research/overview.md` | main agent | trip summary, the traveller's ask, phase status, links to the dimension files |
| `/research/summary.md` | main agent | the traveller-facing overview shown in the chat when research finishes |
| `/research/flights.md` | flights subagent | flight options with offer ids and prices |
| `/research/stays.md` | stays subagent | hotel shortlist with hotel ids, area, price |
| `/research/days/day-N.md` | days subagent | one file per day (`day-1.md`, `day-2.md`, …) |
| `/research/entry-and-season.md` | entry_season subagent | visa/entry rules, climate, packing |
| `/research/budget.md` | budget subagent | budget caps, estimate, expense roll-up |
| `/plan/proposal.json` | main agent | the machine-readable proposal (see the `proposal` skill) |

The per-day files live in the `days/` subdirectory: `/research/days/day-1.md`,
`/research/days/day-2.md`, and so on, numbered from 1.

## Heading conventions

Each Markdown file starts with a single H1 naming the dimension **in the traveller's
language**, e.g. `# Flights` / `# Chuyến bay` or `# Day 1 — <city>` / `# Ngày 1 — <city>`.
Use H2 for sections within the file. Headings, prose and notes are all in the
traveller's language; only paths, ids and tool names stay as they are. Keep prose tight; prefer short
paragraphs and bullet lists over long narration. A dimension file that a tool returned
nothing for still exists, with an H1 and a one-line note stating what was searched and
that the tool returned no results (see the dimension skill for the exact wording).

## Citation rule (load-bearing)

**Every factual claim names the tool that produced it.** A price, a date, an id, an
availability, a distance, a weather figure, a visa rule — each is followed by the tool
that returned it, in parentheses: `(search_flights)`, `(get_weather)`, `(get_visa)`.

- If no tool produced a statement, it is not a fact and does not belong in the dossier.
  Do not write prices, dates, ids, or availabilities from memory or inference.
- When a tool returns nothing, say so and name the tool: "No offers returned
  (search_flights)."
- The grader checks that every dimension file cites tools; an uncited claim fails the
  rubric.
- Tool names appear **only** inside those citation parentheses — never in a sentence
  ("I searched with `search_places`…"). The traveller reads these files with the
  citations stripped, so a tool named in prose is left behind as jargon.

## Ids section (load-bearing)

The traveller never sees an id, but the proposal is assembled from them. So every
dimension file that cites items **ends with an `## Ids` section** (that exact English
heading, always last) and ids appear nowhere else in the file:

```markdown
## Ids

- Cham Hotel Danang: 77a8ed7c-78d0-5eb2-82e5-cf29d90c8705
- VN456 SGN→DAD 2026-10-25: 38382e5c-a32e-5d1e-9d08-8d2d69c51dca
```

One line per item you recommend or list, `<name as written above>: <id>`, copied from the
tool's "Ids for the proposal" list. In the body, refer to items by name only.

## Overview file

`/research/overview.md` is the reader's entry point. It holds:

- the trip (destination, dates if known, party) drawn from `get_trip_summary`
  (cite it);
- the traveller's ask in one or two lines;
- a phase checklist mirroring the todos (which dimensions are done);
- a short pointer line to each dimension file that exists.

It never duplicates the dimension bodies — it links to them.

## Summary file

`/research/summary.md` is what the traveller reads first — in the chat, not the Research
tab. Write it last, for a person, not for the grader:

- at most 5 bullets and about 100 words, in the traveller's language;
- one bullet per highlight worth deciding on, each opening with a short bold label
  (`**Flights:**`, `**Stay:**`, `**Days:**`, `**Budget:**`, `**Season:**`, in the
  traveller's language): the best flight, the recommended stay and area, the shape of the
  days, the budget picture vs. any cap, one entry/season note that matters;
- plain words only — no headings, tables, ids, file paths or `(tool)` tags. It restates
  facts already cited in the dimension files; never add a fact that is not in them;
- when a dimension found nothing, say so in one short bullet instead of guessing.

## Revise turns

On a later turn, do not rewrite files. Use `edit_file` to change only the lines that
change, preserving citations. The layout and paths above never change between turns.
