# research-dossier-reader — Summary

Lane: normal
Confidence: high
Reason: a pure text transform on two traveller-facing reads, a research model middleware, skill text and grader v2; no access-control change, no migration, no new endpoint.
Flags: none
Affects: app/research (reader, agent middleware, skills, service), research files route, grader prompt
Input-type: change request

### Intent

> hiện tại research files đang chưa những info như là id và tool name. cái này ko nên xuất hiện cho user thấy. Và ngôn ngữ của research files ko match đúng vs ngôn ngữ của user

(context: http://localhost:3000/trips/c26e4907-f068-4107-9780-e8edef0dc016?tab=research)

## What changed

Run `0f71586a` (Đà Nẵng) was the first valid live run — SGN→DAD / DAD→SGN searched one leg at a
time, a 15-stop proposal with real ids, grader `satisfied` — but its files were full of
`(search_flights)` tags and `offer_id \`…\``, and every dimension file was English under a
Vietnamese summary. **Reader view:** `app/research/reader.py::reader_view` drops citation
parentheses made only of tool/source names, labelled ids, lines that only list bare ids, and the
trailing `## Ids` section; the `.md` file route and the chat summary serve it (JSON untouched).
The stored dossier keeps citations and ids for the grader and the proposal. **Language:**
`_WriteInTravellerLanguage` appends "Write every file and note in <language>" to every research
model call (main + subagents) from `state["language"]`. **Skills:** ids only in a trailing
`## Ids` section, tool names only inside citations, headings in the traveller's language.
**Grader v2:** criterion 5 fails any single off-language file; new criterion 6 for readable bodies.

### Rationale

Stripping at read time keeps the grader's anti-fabrication citations intact; moving ids to a
trailing section makes that strip clean for new dossiers, while the line-drop keeps old ones from
reading "shortlist:,, and.". Subagents only see task text, so language had to travel through state.

### Alternatives considered

- Drop citations from the dossier — rejected: they are the grader's evidence and the model's own anti-fabrication discipline.
- Translate files on read — rejected: a model call per read, and the source stays in the wrong language.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_reader.py -q` | 0 | 12 passed on lines from the live run | SC-1 |
| behavior | `reader_view` over the live Đà Nẵng `stays.md` / `flights.md` / `summary.md` in `api-api-1` | 0 | tags and ids gone; bare-id lines dropped | SC-1 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/research/test_routes.py tests/agents/test_research_node.py -q` | 0 | `.md` served clean, `proposal.json` keeps ids; chat summary stripped | SC-2 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_language.py -q` | 0 | vi/en named, no-language passthrough, async, every subagent bound | SC-3 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q` | 0 | grader v2 active; `## Ids` in layout + 3 skills | SC-4 |
| full BE suite | `pytest --rootdir apps/api -c apps/api/pyproject.toml apps/api/tests` from a cwd without `apps/api/.env` | 0 | 3035 passed, 9 skipped | |
| full web suite | `cd apps/web && pnpm vitest run` | 0 | 393 passed | |

### Not auto-verified

- A real run now writes Vietnamese dimension files and an `## Ids` section — needs one paid run.
- Editing a file in the tab saves the reader view, so that file loses its `## Ids` (the proposal is unaffected).
- The live-progress chips still show raw tool names and the grader's English explanation (not in this scope).

### Rollback

- `git revert <sha>`; `active.yaml` trip_research_grader → 1.

### Harness-Delta

- none
