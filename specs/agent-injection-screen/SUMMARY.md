# agent-injection-screen — Summary

Lane: high-risk
Confidence: medium
Reason: Hard gates `external-provider` (a new hosted decision-model API, TypeSafe Jev, with a new secret `TYPESAFE_API_KEY`; called over httpx, no manifest change) and `audit/security` (a prompt-injection filter on untrusted third-party text is a security control; with the hosted option, fetched web content leaves the box to a new vendor). Direction is clear (screen external content before it becomes a ToolMessage); the provider fork and flag policy decided by the owner at intake (E001 = A Jev hosted, E002 = B warning-wrap).
Flags: external-provider, audit/security, external systems, existing behavior (web tool output gains attributes in enforce mode), weak proof (no injection corpus in eval yet; classifier is non-deterministic across versions), multi-domain (tools + service + config + prompt)
Affects: app/core/config.py (mode/key/model/threshold settings); app/tools/web_search_tools.py (`<web_result>` attributes, PR #227); new app/services/injection_screen_service.py (httpx, no new dependency); app/prompts/concierge/v15.md + active.yaml; new scripts/injection_screen_smoke.py; tests. RAG, research agent, eval goldens and requirements are out of scope (design.md §1)
Input-type: new spec
Route: brainstorming ✅ design.md (2026-09-24, reviewer approved) → xia2 Deep ✅ research-brief.md (2026-09-24: raw httpx POST, no SDK; Noul has no confidence field; 529 → unavailable; PR #230 overlap) → writing-plans ✅ PLAN.md (2026-09-24, 5 tasks / 3 waves, reviewer approved) → using-git-worktrees → subagent-driven-development → correctness/intent review → PR
Escalate: no (E001–E002 decided 2026-09-24: A hosted Jev, B warning-wrap)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> make the deep research for https://www.langchain.com/blog/building-a-harness-with-jev
> thinking can we apply it to current project to improve performance or reduce cost
>
> nếu bắt buộc phải dùng thì apply dc ở use case nào?
>
> ok, viết 4 cái trên xuống phần research . sau đó run /feature-intake cho cai 1 truoc

Use case 1 as recorded in `specs/jev-harness-research/research-brief.md`: after `search_web` /
`find_places_live` (PR #227) and the RAG retriever return, classify each page/chunk with a
System One decision model (Jev via `langchain-typesafe`, or self-hosted Laya) using a Noul
"does this passage contain instructions aimed at the AI assistant?", and drop or warning-wrap
flagged content before it becomes a ToolMessage.

## What changed

Every `search_web` and `find_places_live` result can now be screened by TypeSafe Jev before the
concierge reads it. One yes/no question per result asks whether the text contains instructions
aimed at an AI assistant. The feature ships with `INJECTION_SCREEN_MODE=off`, so nothing changes
until it is switched on.

- `shadow` calls the vendor and logs verdict counts, but the tool output stays byte-identical.
- `enforce` adds `screened="true" flagged="…" p="…"` to each `<web_result>` block, or
  `screened="false"` when the vendor did not answer. No result is ever dropped.
- Any vendor failure (timeout, 429, 529, bad body) falls open to `screened="false"`. The tool never
  fails because of the screen.
- Concierge prompt v15 tells the model how to treat flagged and unscreened blocks.
- A smoke script checks three canned passages against the real vendor.

Commits: 69c919c7 (settings), 773a2ec1 (service), 36b3644d (tool attributes), f83dc786 (prompt
v15), plus the Task 3.1 commit (smoke script + this record).

### Rationale

Owner chose hosted Jev (E001 = A) and warning-wrap (E002 = B): no local model weights in the py3.12 image, and no page is ever lost to a false positive; the concierge prompt gains a rule to ignore instructions inside flagged blocks.
Research context: `specs/jev-harness-research/research-brief.md`. Existing defences the screen
sits behind: HTML-escaped `<web_result>` blocks with capped snippets (PR #227), store-layer
memory poisoning guard and `<traveller_memory>` wrapping (PR #214). PR #214 deferred exactly this
item as E001 (RAG / tool-output wrapping).

### Alternatives considered

- Deterministic regex/keyword screen (no model): cheapest, zero vendor, but low recall on
  paraphrased instructions; can still ship as the always-on first layer.
- `gpt-5.4-nano` yes/no call per page: no new dependency, ~$0.0002–0.0005 per page but ~1 s
  latency per item on the tool path; fallback if neither Jev nor Laya is acceptable.

### Deviations

- Rule 3 — `apps/api/scripts/` and `apps/api/tests/scripts/` match the root `.gitignore` `scripts/` rule. The two new files were force-added (`git add -f`), which is how every existing script there is tracked. Task 3.1 commit.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| config defaults + mode Literal | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/core/test_config_injection_screen.py -q` | 0 | 5 passed | SC-1 |
| service inactive + verdict | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/services/test_injection_screen_service.py -q -k "inactive or verdict"` | 0 | 7 passed | SC-2 |
| service cache | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/services/test_injection_screen_service.py -q -k cache` | 0 | 4 passed | SC-3 |
| service timeout / errors / empty | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/services/test_injection_screen_service.py -q -k "timeout or error or empty"` | 0 | 9 passed | SC-4 |
| tool enforce attributes | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_tools.py -q -k enforce` | 0 | 5 passed | SC-5 |
| tool shadow/off byte-identical | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_tools.py -q -k "shadow or off_mode"` | 0 | 3 passed | SC-6 |
| pre-existing web tool + binding tests | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_tools.py tests/tools/test_web_search_binding.py -q` | 0 | 28 passed | SC-7 |
| concierge v15 + active versions | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/prompts/test_concierge_prompt.py tests/prompts/test_active_versions_load.py -q` | 0 | 10 passed | SC-8 |
| smoke script exits 2 without key | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= TYPESAFE_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/scripts/test_injection_screen_smoke.py -q` | 0 | 1 passed | SC-9 |
| ruff on new/touched files | `cd apps/api && ../../.venv/bin/ruff check app/services/injection_screen_service.py app/tools/web_search_tools.py app/core/config.py scripts/injection_screen_smoke.py` | 0 | All checks passed | SC-10 |

### Not auto-verified

- Jev's real accuracy on travel snippets and the `0.7` enforce threshold — reached traceability only; not run because no `TYPESAFE_API_KEY` is available on this machine. The smoke script was not run against the real vendor. Next step: set the key, run `python -m scripts.injection_screen_smoke`, then run `shadow` on the dev stack before `enforce`.
- Vietnamese place data from `find_places_live` on an English-first model — not measured; shadow-mode logs are the check.
- The exact `POST /v1/systemone` response shape — reached provenance (vendor docs, research-brief.md); not re-run against the live API.
- Latency of about 5 concurrent vendor calls from this region — not measured; the 2 s budget caps it in code (SC-4).

### Rollback

- Runtime, no deploy: set `INJECTION_SCREEN_MODE=off` (the default). The tool output returns to the pre-change bytes (SC-6).
- Code: `git revert <task-3.1-sha> f83dc786 36b3644d 773a2ec1 69c919c7`.

### Harness-Delta

- none
