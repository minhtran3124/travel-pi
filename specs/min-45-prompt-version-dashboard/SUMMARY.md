# min-45-prompt-version-dashboard — Summary

Lane: normal
Confidence: high
Reason: Read-only server-rendered dashboard section reusing the existing `/dashboard/*` Jinja2 pattern — no auth, no DB/persistence, no migration, no external provider, no public JSON contract (HTML routes are `include_in_schema=False`); the only touched shared file is additive read helpers on `PromptRegistry`. Weak-proof flag fires (new diff/404 paths need tests). Normal (not tiny) because it spans a new router + 3 templates + registry helpers + wiring + tests.
Flags: weak-proof
Affects: app/prompts/registry.py (shared runtime prompt loader — additive read methods only), app/routers/dashboard.py surface + app/main.py router wiring
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-45, verbatim from Linear. -->

**BE dashboard: prompt version manager with 2-way diff view**

## Context

We already version every LLM prompt on disk under `apps/api/app/prompts/<name>/v{N}.md`, tracked via `app/prompts/registry.py` (`PromptRegistry`) and the active-version map in `app/prompts/active.yaml`. There's no UI to browse them today — reviewing a prompt or diffing two versions means opening files by hand.

We already have a server-rendered dashboard pattern for this: `GET /dashboard/hotels` (see `app/routers/dashboard.py` + `app/templates/hotels.html`) — Jinja2 HTML routes under `/dashboard`, `include_in_schema=False`, browsable card grid with filters. Reuse that pattern rather than building a new stack.

## Goal

Add a read-only `/dashboard/prompts` section to browse every registered prompt name, inspect any version's content, and diff exactly two versions side-by-side.

## Scope

**Coverage**: all prompt names currently in `app/prompts/` — `supervisor`, `planner`, `concierge`, `booking`, `budget`, `journal`, `reflection`, `communication_style`, `memory_extraction` — driven dynamically off `PromptRegistry.names()`, not a hardcoded list, so new prompt dirs show up automatically.

**Pages**:

1. `GET /dashboard/prompts` — card/list grid of all prompt names, showing each name's active version (from `active.yaml`) and total version count.
2. `GET /dashboard/prompts/{name}` — version list for one prompt name (v1..vN), flag which one is "active," rendered markdown content on select.
3. `GET /dashboard/prompts/{name}/diff?from=vX&to=vY` — side-by-side or unified diff between exactly 2 versions of the same prompt. Reject/ignore a 3rd version param — 2-way compare only, by design (no multi-version diff UI).

**UI**:

* Friendly, easy-to-scan layout consistent with existing dashboard pages (same base template/tokens per `DESIGN.md`).
* Diff view highlights added/removed/changed lines (line-level diff, e.g. Python `difflib` server-side rendered to HTML — no new JS dependency needed).
* Version picker limited to 2 selectors (from/to) to enforce the 2-version-only constraint.

## Non-goals

* No write/edit UI — prompts stay file-authored; this is browse + diff only, not a prompt editor.
* No new persistence — reads directly from `PromptRegistry` (in-memory, file-backed), same as runtime prompt loading.
* No change to `active.yaml` semantics or the registry's `get()` API.
* No auth (matches existing project convention: no auth/pagination/rate-limiting anywhere yet).

## Suggested approach

* New router `app/routers/dashboard_prompts.py` (or extend `dashboard.py`) using the existing `PromptRegistry` singleton — no DB/service layer needed since prompts aren't DB-seeded.
* New templates `prompt_list.html`, `prompt_detail.html`, `prompt_diff.html` under `app/templates/`, following `hotels.html` conventions.
* Diff rendering: `difflib.HtmlDiff` or a lightweight custom line-diff table for cleaner styling — evaluate both against `DESIGN.md` before picking.

## Acceptance criteria

- [ ] `/dashboard/prompts` lists every name from `PromptRegistry.names()` with active version + version count.
- [ ] `/dashboard/prompts/{name}` shows all versions for that name, active version flagged, content rendered.
- [ ] `/dashboard/prompts/{name}/diff?from=v{X}&to=v{Y}` renders a clear line-level diff between exactly those 2 versions.
- [ ] Unknown prompt name or version → 404, not a 500.
- [ ] New prompt dirs/versions added to `app/prompts/` appear without code changes (dynamic, not hardcoded).
- [ ] Follows existing `/dashboard/*` HTML-route conventions (`include_in_schema=False`, Jinja2, matches `DESIGN.md` tokens).

## What changed

Adds a read-only `/dashboard/prompts` section (list → detail → 2-way diff) reusing the existing `/dashboard/*` Jinja2 pattern, driven dynamically off `PromptRegistry`. New: additive `PromptRegistry.versions()`/`active_version()` (get() untouched); a pure `app/core/prompt_diff.build_line_diff()` over `difflib.SequenceMatcher` producing a themeable unified + aligned side-by-side row model; three token-styled templates; a `dashboard_prompts.py` router (registry `KeyError`→`NotFoundError` so unknown name/version is 404 not 500; `from`/`to` via `Query(alias=...)`, 3rd param ignored); and a "Prompts" entry in the dashboard tab bar + ⌘K palette. Content shown as raw escaped source (no markdown render, no new dependency). Shipped in 4 waves (`8edc6dc`, `d989a3e`, `12a8f07`, `2f9c86c`).

### Rationale

The registry + on-disk versioning already exist; the lightest credible path is a thin new router + 3 templates that read `PromptRegistry`, plus two additive read helpers (`versions(name)`, `active_version(name)`) since the registry today exposes only `get()` + `names()`. A separate `dashboard_prompts.py` router avoids editing the large existing `dashboard.py`. No DB/service layer, no schema, no auth — matching project convention.

### Alternatives considered

- Diff rendering — `difflib.HtmlDiff` (built-in, but emits its own hard-to-theme table markup) vs a custom `difflib`-driven line-diff table rendered through the dashboard's own tokens. **DECIDED (human, via A/B mockup): custom themed table** — `difflib.SequenceMatcher` opcodes → our own row model, styled with dashboard tokens, offering unified + side-by-side with no new JS dependency. `HtmlDiff` rejected: its baked-in white table + `#aaffaa/#ffff77/#ffaaaa` palette ignores `DESIGN.md` and is unreadable in dark mode. Mockup: `scratchpad/prompt-diff-mockup.html` → https://claude.ai/code/artifact/74494d6a-caf0-44a6-b0db-c2f4512125df
- Extend `dashboard.py` vs new `dashboard_prompts.py` router — leaning new file (surgical, keeps the 800-line dashboard.py untouched).

### Deviations

- Rule 3 — `ruff-on-edit` hook stripped the new `dashboard_prompts` import from `app/routers/main.py` on first write (import added before its usage line existed), causing a transient `F821`. Re-added once the `include_router` line was present. Matches the known `ruff-on-edit-strips-unused-imports` gotcha. Wave 3.
- Design deviation (human-approved, not a Rule 1–3 auto-fix) — detail page shows **raw escaped source**, not rendered markdown, versus the issue's "rendered markdown" wording. Confirmed before implementation; avoids a new dependency and preserves prompt fidelity.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Prompt suite (SQLite) | `cd apps/api && DATABASE_URL="sqlite:///./t.db" ../../.venv/bin/python -m pytest tests/api/prompts/ -q` | 0 | 22 passed (10 unit + 12 route) |
| Routes render + 404s | inline TestClient smoke over all 3 routes + error paths | 0 | list/detail/diff → 200; unknown name/version/malformed → 404; 3rd param → 200 |
| Lint | `cd apps/api && ruff check app/routers/dashboard_prompts.py app/core/prompt_diff.py tests/api/prompts/` | 0 | clean |
| Independent review | reviewer agent (correctness + intent) | — | no defects; all 6 acceptance criteria met; non-goals respected |

> Test note: the local `apps/api/.env` sets `DATABASE_URL` to a non-running Postgres (:5433); the suite runs on SQLite, so override `DATABASE_URL="sqlite:///..."` (or move `.env` aside) — matches `env-openai-key-test-breaks-llm-tests`.

### Rollback

- `git revert <sha>` (additive read-only feature; no migration/data change)

### Harness-Delta

- backlog — `.env`'s `DATABASE_URL=postgres:5433` silently breaks `make test`'s "SQLite" promise (lifespan seeds the configured DB on `TestClient` startup). Worth a documented `TEST_DATABASE_URL`/`.env.test` convention so ad-hoc `pytest` invocations don't hit a dead Postgres. → `/compound`.
