# gh-229-research-web-search — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-24
- trigger: ambiguous-direction
- question: How should a web-sourced fact be cited in the dossier, given that the reader strips `(tool)` citations before the traveller sees the file?
- context: dossier-format rule — every fact names its tool in parentheses. Grader criterion 6 — tool names only inside citations.
- options:
  - A) (recommended) Cite `(search_web)` / `(find_places_live)` like any other tool. Each file that used the web also ends with a `## Sources` section of markdown links `[title](url)`, so the traveller keeps the URLs after the citations are stripped. The reader and grader change is small and explicit.
  - B) Inline `[title](url)` next to the fact, plus the `(search_web)` citation. The link survives, but it clutters the prose and needs a reader check that link syntax is not mangled.
  - C) Only `(search_web)`. The traveller loses the source link.
- default_if_no_response: BLOCK
- decision: A (user reply "E001 A, E002 A, E003 A")
- decided_by: Minh Tran
- decided_at: 2026-09-24

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-24
- trigger: ambiguous-direction
- question: Should the grader check web-sourced facts?
- context: trip_research_grader v2 criterion 1 fails an uncited fact. Web facts may otherwise slip in without a source.
- options:
  - A) (recommended) New grader version: a fact cited to a web tool must have its URL in `## Sources`, and no price may be cited to a web tool.
  - B) No grader change; rely on the skill rules.
- default_if_no_response: BLOCK
- decision: A (user reply "E001 A, E002 A, E003 A")
- decided_by: Minh Tran
- decided_at: 2026-09-24

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-24
- trigger: hard-gate (external provider cost)
- question: How should the cost of web calls from one research run be bounded?
- context: Today there is one per-user bucket (30 an hour) shared with chat, and SerpAPI is on the Free plan (250 a month). One run has 5 subagents and possible revise turns.
- options:
  - A) (recommended) Keep the shared per-user bucket and add a per-run cap: at most 6 web calls per research run, counted in run state. Past the cap the tool returns "web budget for this run is used up" and the agent continues with seeded data.
  - B) Shared bucket only (as #227 shipped).
  - C) A separate `web_search_research` bucket.
- default_if_no_response: BLOCK
- decision: A (user reply "E001 A, E002 A, E003 A")
- decided_by: Minh Tran
- decided_at: 2026-09-24
