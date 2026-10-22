# research-chat-summary — Summary

Lane: normal
Confidence: high
Reason: research-agent prompt v2 + skill text, chat launcher reply, web card; no auth, schema, migration or new endpoint (FE reads the existing files route).
Flags: none
Affects: app/research (prompt, skill, runner input, launcher), apps/web chat card
Input-type: change request

### Intent

> hiện tại có 1 vấn đề nữa là sau khi mà research xong thì ngoài việc báo xong, thif chúng ta nên tổng hợp lại đưa cho user review tổng quan và hướng họ đến tab research để xem chi tiết.

Decisions (AskUserQuestion): the research agent writes the summary itself (`/research/summary.md`),
and it is shown in the chat's research-done card.

## What changed

The research agent (trip_research **v2**) writes `/research/summary.md` last: ≤5 bullets, each
with a bold label, in the traveller's language, restating only cited facts. The runner appends
`Language: <name>` to every turn message (the model never saw the language before), and the chat
launcher now passes the chat language to `launch`. When a run is done, the chat reply is the
"done" copy plus the summary (`ResearchService.completed_summary`), and the web card renders the
summary as tight bullets with a "See all the details →" button to the Research tab; with no summary
(older dossier / read failure) it keeps the hint + section chips.

### Rationale

The agent already holds the whole dossier in context at its last step, so a traveller-facing
summary costs no extra call. The model was never told the traveller's language (only tools read
`state["language"]`), although the grader rubric requires the dossier in that language, and the
chat launcher never passed the chat language to the run — both are fixed so the summary reads in
the traveller's language.

### Alternatives considered

- Separate summarizer LLM call in the runner — rejected by the user: extra call per run plus a new agent-config node.
- Summary as a persisted chat message — rejected by the user: the run does not know the chat conversation.

### Deviations

- Rule 1 — `tests/research/test_resume.py` pinned the exact turn message; updated for the `Language:` line.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py -q` | 0 | `Language:` line for vi/en/unknown; failed before the change | SC-1 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q` | 0 | v2 active; prompt + layout name summary.md | SC-2 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | 0 | 18 passed: summary appended; none → copy only; launch gets language | SC-3 |
| unit (web) | `cd apps/web && pnpm vitest run src/components/chat` | 0 | 173 passed: summary shown, read failure keeps hint, no fetch without summary.md | SC-4 |
| full BE suite | `pytest --rootdir apps/api -c apps/api/pyproject.toml apps/api/tests` from a cwd without `apps/api/.env` | 0 | 2984 passed, 9 skipped | |
| typecheck + lint | `cd apps/web && pnpm exec tsc --noEmit -p . && pnpm lint`; `cd apps/api && ruff check app scripts` | 0 | 0 errors | |
| visual | Node 24 playwright-core screenshot of a temporary preview route (removed) | 0 | light + dark; hanging bullets, no clipping | |

### Not auto-verified

- The real model writes `/research/summary.md` in the traveller's language — needs one paid run.

### Rollback

- `git revert <sha>` per commit; `active.yaml` trip_research → 1.

### Harness-Delta

- none
