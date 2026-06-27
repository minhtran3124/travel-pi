# Deep Review — Agent Prompts (`app/prompts/`)

**Date:** 2026-06-27
**Reviewer:** Claude (deep prompt review)
**Scope:** the seven prompts served by the file-backed registry —
`supervisor`, `concierge`, `planner`, `journal`, `booking`, `budget`, and the
shared `communication_style`.
**Outcome:** each prompt rewritten as a structured `v2.md`; `active.yaml` flipped
to v2. v1 retained for rollback / A-B.

---

## How prompts are wired (context)

- `app/prompts/registry.py` — walks `prompts/<name>/v*.md`, reads `active.yaml`
  (`name -> version`); `registry.get(name)` returns the active version's text.
- `app/agents/subagents/_base.py` — **prepends `communication_style` to every
  sub-agent prompt**: `SystemMessage(f"{style}\n\n{prompt}")`. So the house style
  is shared; each domain prompt is a "role card" layered on top.
- `app/agents/supervisor.py` — uses `supervisor` alone (no style prepend) because
  it only emits a structured routing decision, never user-facing text.

---

## Findings (v1)

### F1 — No consistent structure across prompts
`planner`, `journal`, `booking`, `budget` are 4–6 lines of unstructured prose.
There is no role heading, and responsibilities / working steps / guardrails are
run together in one paragraph. Hard to scan, hard to extend, and easy for a
model to under-weight a buried constraint (e.g. booking's "never book without
confirmation").

### F2 — `concierge` duplicates the shared house style
The concierge prompt re-states rules that already live in `communication_style`:
the inline-`-` separator rule and "never dump every field as a list". Because the
style block is prepended at runtime, every concierge call carried these rules
**twice**. Duplication means the two copies drift over time and waste tokens.
The genuinely concierge-specific part — the weather BAD/GOOD example — is worth
keeping; the generic restatements are not.

### F3 — `communication_style` formatting list is redundant
Four overlapping bullets all say the same thing:
> Use list options for selection. · Use **bold** for options for selection. ·
> Use **bold** for selected options. · ... · When presenting options, list them
> as bullets and clearly indicate any selection.

These collapse into one coherent rule about options & selection.

### F4 — Role / output framing missing on the router
`supervisor` lists the targets well but doesn't separate **role**, **routing
rules**, and **output contract** (it must emit only a structured decision,
matching `SupervisorIntent{target_agent, language}`). The language-detection
requirement isn't stated in the prompt at all even though the schema asks for it.

### F5 — Guardrails not surfaced
"Confirm before large changes" (planner), "never book without confirmation"
(booking), "don't invent specifics" (concierge) are real guardrails buried in
prose. Pulling them under an explicit `## Guardrails` heading raises their
salience.

---

## v2 changes

Common template applied to every domain prompt:

```
# Role: <name>
<one-line identity>
## Responsibilities
## How to Work        (numbered when sequential)
## Guardrails         (never / always)
```

Per-prompt:

- **supervisor** — split into Role / Specialist Sub-Agents / Routing Rules;
  added the "output only the structured decision" + "detect language" rules to
  match `SupervisorIntent`. (F4)
- **concierge** — removed the duplicated house-style rules (F2); kept the
  weather BAD/GOOD example as the one domain-specific illustration.
- **communication_style** — same substance, restructured under
  `## How to Talk`, `## How to Format` (with a `### Markdown needs blank lines`
  sub-section), `## Honesty and Wrap-Up`; redundant option/bold bullets merged. (F3)
- **planner / journal / booking / budget** — promoted to the common template;
  guardrails surfaced (F1, F5). No behavioural rules dropped.

**Nothing was weakened** — every existing instruction survives in v2, just
relocated under a clear heading or merged with its duplicate.

---

## Verify

| Check | Command | Result |
|---|---|---|
| Registry loads v2 as active | `pytest tests/prompts/test_registry.py -x` | see Status |
| Agent suite still green on FakeLLM | `pytest tests/agents -x` | see Status |

## Rollback

Revert `active.yaml` to all `1` (or `git revert <sha>`); v1 files are untouched.
