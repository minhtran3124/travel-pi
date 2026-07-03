---
problem_type: decision
module: agent/reflection
tags: langgraph, message-roles, reflection-loop, category-matching, fuzzy-match, prompt-versioning
severity: critical
applicable_when: Adding or debugging a free-text agent-tool argument that must map to a fixed set of DB values, or injecting a programmatic/internal instruction into a LangGraph agent's state["messages"].
affects:
  - apps/api/app/services/place_service.py
  - apps/api/app/agents/nodes.py
supersedes: null
confidence: high
confirmed_at: 2026-07-03
---

## Applicable When

Apply when working on LangGraph multi-agent nodes that inject synthetic messages into
`state["messages"]` (e.g. reflection/revision loops, retry prompts) — use
`SystemMessage` (not `HumanMessage`) for internal directives so language-detection /
"latest message" prompt rules aren't fooled; and when a free-text tool argument (e.g.
category, cuisine, amenity type) must resolve to a fixed DB value set that an LLM may
not emit exactly (plurals, typos, casing).

## Decision 1

### Context
`search_places(category='cafes')` returned zero results for a legitimate café query
because `PlaceRepository.search()` in `apps/api/app/repositories/place_ref.py` does an
exact (case-insensitive) match — `Place.category == category.strip().lower()` — and
the seeded DB only has the singular `"cafe"`, but the LLM tool-caller emitted the
plural `"cafes"`. The category argument is free text chosen by the model at call
time, so it can't be constrained to always match the DB's exact casing/plurality.

### Options Considered
- Option A: Tool-schema hint only — add an enum/pattern of valid categories into
  `SearchPlacesArgs.category`'s docstring to nudge the model toward the exact
  canonical string, with no backend fallback.
- Option B: Backend fuzzy-match — add `PlaceService.resolve_category()` using the
  existing `best_match()` helper (`app/core/text.py`, difflib-based) against
  `CATEGORY_META`'s keys, wired into `search_places()` so an unresolved category
  short-circuits to `[]` — the same contract `resolve_city()` already uses for city
  names.
- (Option C, implicit: both A and B combined, or leaving it unfixed — the option set
  explicitly offered was "fuzzy-match", "tool description enum", "both", or "don't
  fix".)

### Decision & Rationale
Chose Option B (backend fuzzy-match in `PlaceService`). Correctness should not depend
on the model reliably emitting one exact string every time — a backend fuzzy-matcher
is robust regardless of what free-text variant the LLM produces (plural, typo, case).
It also reuses the exact mechanism (`best_match()`) and the exact "unresolvable →
empty result" contract that `resolve_city()` already established in the same file, so
the codebase gains a second instance of one pattern instead of a second, prompt-only
mechanism for the same class of problem.

### Applicable When
A future engineer adds or debugs another free-text argument on an agent tool (e.g.
amenity type, cuisine, price tier) that must map to a fixed set of DB values and is at
risk of exact-match misses from LLM-generated plurals/typos/casing.

### Consequences
Enables: category resolution is now typo/plural-tolerant and consistent with city
resolution; adding a new category to `CATEGORY_META` doesn't require a corresponding
prompt/schema update to stay matchable. Constrains: fuzzy matching can still silently
resolve to the wrong canonical category on ambiguous free text (same known trade-off
`resolve_city()` already carries) — inherited, not a new risk introduced by this
change.

## Decision 2

### Context
`make_reflection_node` in `apps/api/app/agents/nodes.py` injects a follow-up
instruction into `state["messages"]` when the reflection verdict is REVISE. It had
been added as `HumanMessage(content="Please improve your previous answer.")`. The
sub-agent's prompt treats "the traveller's latest message" as authoritative for reply
language; because this injected message was structurally a `HumanMessage` (in
English), the model would silently switch its reply language to English on any
revision pass, even mid-Vietnamese-conversation.

### Options Considered
- Option A: Keep the message as `HumanMessage`, but reword its content to explicitly
  say "keep the same language" — relies on the model correctly parsing an aside
  embedded in what structurally still looks like traveller speech; fragile because the
  language-detection rule keys off message role/recency, not content parsing.
- Option B: Change the message's role to `SystemMessage` (import already available in
  the file) so it is no longer "the traveller's latest message" at all, structurally
  excluding it from the language-detection rule, plus keep an explicit textual
  reminder as a second layer of defense.

### Decision & Rationale
Chose Option B — reclassify the injected revision note as a `SystemMessage`, not just
reword it. Deciding factor: the bug was a structural/mechanism-level problem (an
internal control-flow message impersonating traveller input), so the fix needed to be
structural too — closing it at the message-role level rather than hoping the model
reliably parses a caveat inside content it should otherwise ignore. This matches how
the rest of the LangGraph state already distinguishes system/human/AI roles for
control flow, rather than introducing a new content-based convention.

### Applicable When
A future engineer injects any programmatic/internal instruction into
`state["messages"]` in this LangGraph agent (reflection, retries, follow-up nudges)
and needs it to NOT be treated as "the user's latest turn" for language detection,
intent parsing, or any other rule that keys off message role/recency.

### Consequences
Enables: internal control messages can be added to the conversation without risk of
being misread as user input for role-sensitive logic (language, tone, intent).
Constrains: any other rule in the prompts that currently assumes "last message ==
traveller" must be checked against this same class of internally-injected message
going forward — this fix covers language detection, but the general pattern (system
messages for internal notes) needs to be followed consistently for future injections.

## Related

- [reflection-humanmessage-language-flip](reflection-humanmessage-language-flip.md)
- [langgraph-thread-reset-and-prompt-reload](langgraph-thread-reset-and-prompt-reload.md)
- [local-postgres-checkpointer](local-postgres-checkpointer.md)
