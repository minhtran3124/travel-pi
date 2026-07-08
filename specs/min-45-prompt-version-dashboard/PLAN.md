---
slug: min-45-prompt-version-dashboard
status: active
owner: Minh Tran
created: 2026-07-08
---

# MIN-45 — Prompt version dashboard with 2-way diff

## 1. Motivation

Add a read-only `/dashboard/prompts` section so prompts under `app/prompts/<name>/v{N}.md`
can be browsed, inspected, and diffed in the browser instead of by opening files by hand.
Reuses the existing `/dashboard/*` Jinja2 pattern (`include_in_schema=False`), driven
dynamically off the in-memory `PromptRegistry` — no DB, no auth, no persistence.

Three pages: **list** (all names + active version + count) → **detail** (versions for one
name, active flagged, content shown) → **diff** (line-level, exactly two versions).

## 2. Non-goals

- No write/edit UI (prompts stay file-authored).
- No new persistence; no change to `active.yaml` semantics or `registry.get()`.
- No auth / pagination / rate-limiting (matches project convention).
- No multi-version diff — exactly two versions; a 3rd param is ignored.

## 3. Success Criteria (from the issue's acceptance list)

- `/dashboard/prompts` lists every `PromptRegistry.names()` with active version + version count.
- `/dashboard/prompts/{name}` shows all versions, active flagged, content displayed.
- `/dashboard/prompts/{name}/diff?from=v{X}&to=v{Y}` renders a clear line-level diff of those two.
- Unknown name/version → **404, not 500**.
- New prompt dirs/versions appear with no code change (dynamic off the registry).
- Follows `/dashboard/*` conventions + `DESIGN.md` tokens.

## 4. Key decisions (locked)

- **Diff rendering** — custom `difflib.SequenceMatcher` row model → our own themed table
  (unified + side-by-side), no new JS dep. (Human-approved via A/B mockup; see SUMMARY.)
- **Content display** — **CONFIRMED (human): raw prompt source** in a styled `<pre>` (Jinja
  auto-escaped), **not** rendered HTML markdown. Higher fidelity for a prompt-inspection tool
  (exact characters the model receives), consistent with the raw line-diff, and avoids adding a
  markdown dependency (none exists today). Deliberate deviation from the issue's "rendered
  markdown" wording, signed off before implementation.
- **Router placement** — new `app/routers/dashboard_prompts.py` (separate `APIRouter`, same
  `/dashboard` prefix), registered next to `dashboard.router` — keeps the 900-line
  `dashboard.py` untouched.

## 5. Tasks

### Task 1.1 — Registry read helpers

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/prompts/registry.py, apps/api/tests/api/prompts/test_prompt_registry_helpers.py</files>
  <action>Add two additive read methods to PromptRegistry (do NOT touch get()/reload()/active.yaml semantics): `versions(self, name: str) -> list[int]` returns `sorted(self._prompts[name])`, raising KeyError(f"Unknown prompt: {name!r}") for an unknown name to mirror get(); `active_version(self, name: str) -> int` returns `self._active.get(name)` or, when absent, `max(self._prompts[name])` (mirrors get()'s active-fallback at lines 72-73), raising KeyError for an unknown name. Add unit tests: versions() returns ascending ints for a known name (e.g. budget → [1,2]); active_version() matches active.yaml (e.g. supervisor → 5) and falls back to max when a name is missing from active.yaml; both raise KeyError on an unknown name.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/prompts/test_prompt_registry_helpers.py -x -q</verify>
  <done>Both helpers return correct values off the eager in-memory maps; get() unchanged; tests pass.</done>
</task>
```

### Task 1.2 — Line-diff helper (SequenceMatcher → themeable row model)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/core/prompt_diff.py, apps/api/tests/api/prompts/test_prompt_diff.py</files>
  <action>Create a pure, dependency-free helper over `difflib.SequenceMatcher`. Define a small dataclass `DiffRow(tag, old_no, new_no, text)` where tag ∈ {"context","add","del"}, and `build_line_diff(old: str, new: str) -> dict` returning `{"unified": list[DiffRow], "left": list[DiffRow|None], "right": list[DiffRow|None]}`: iterate `SequenceMatcher(None, old.splitlines(), new.splitlines()).get_opcodes()` — 'equal'→context rows on both sides; 'delete'→del rows (left only); 'insert'→add rows (right only); 'replace'→del rows left + add rows right; for side-by-side pad the shorter side of a replace/insert/delete block with None so rows align. Keep line numbers 1-based. No intra-line span highlighting in v1 (line-level only — simplest that meets the AC). Unit tests: identical input → all context, no add/del; pure insertion; pure deletion; a replace block produces del+add; line numbers correct; side-by-side left/right lengths equal (padded).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/prompts/test_prompt_diff.py -x -q</verify>
  <done>Helper classifies add/del/context correctly, aligns side-by-side with padding, no external dep; tests pass.</done>
</task>
```

### Task 2.1 — Three templates (list / detail / diff)

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/templates/prompt_list.html, apps/api/app/templates/prompt_detail.html, apps/api/app/templates/prompt_diff.html</files>
  <action>Create three templates extending base.html (override {% block title %} and {% block content %}), following hotels.html conventions and DESIGN.md tokens. prompt_list.html: a card/list grid over `prompts` (list of {name, active, count}); each card links to /dashboard/prompts/{name}, shows active version badge + total count. prompt_detail.html: header with name; a version list (v1..vN from `versions`) flagging `active`, each linking to select; the selected version's raw content in a styled monospace `<pre>` (auto-escaped — no markdown render); a 2-selector from/to picker (plain GET form with two <select>) that submits to the diff route. prompt_diff.html: header (name, vX → vY); render the diff row model — unified table by default with a line-number gutter, +/− sign column, and add/del/context row tints from tokens (green/red translucent), plus a side-by-side variant using left/right columns. Mirror the mockup at scratchpad/prompt-diff-mockup.html for styling intent. Use only existing DESIGN.md tokens; no new JS dependency (a tiny inline toggle for unified/side-by-side is acceptable).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('app/templates')); [e.get_template(t) for t in ('prompt_list.html','prompt_detail.html','prompt_diff.html')]; print('templates parse ok')"</verify>
  <done>All three templates parse under Jinja and extend base.html; styling uses tokens only.</done>
</task>
```

### Task 2.2 — Nav wiring (dashboard tab + ⌘K palette)

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/templates/base.html</files>
  <action>Add a "Prompts" entry to BOTH dashboard navigation lists so the section is reachable and highlights when active: (1) the `<div class="tabs">` list (~base.html:897-907) — add an `<a class="tab ...">` to `/dashboard/prompts`, marked active via the same `path.startswith('/dashboard/prompts')` pattern the siblings use; (2) the ⌘K command-palette `PAGES` array (~base.html:981-992) — add `{ label: "Prompts", href: "/dashboard/prompts" }` matching the existing entry shape. Surgical: touch only these two lists, match surrounding style exactly.</action>
  <verify>cd apps/api && grep -q "/dashboard/prompts" app/templates/base.html && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('base.html'); print('base.html ok')"</verify>
  <done>Both nav lists include a Prompts link; base.html still parses.</done>
</task>
```

### Task 3.1 — Router + registration

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/routers/dashboard_prompts.py, apps/api/app/routers/main.py</files>
  <action>Create `dashboard_prompts.py`: `router = APIRouter(prefix="/dashboard", tags=[Tags.dashboard], include_in_schema=False)` and its own `_TEMPLATES = Jinja2Templates(directory=.../templates)` (mirror dashboard.py:62-66). Import `from app.prompts.registry import registry`, `from app.core.prompt_diff import build_line_diff`, `from app.exceptions import NotFoundError`. Routes: (a) GET "/prompts" → build `[{name, active: registry.active_version(name), count: len(registry.versions(name))} for name in sorted(registry.names())]`, render prompt_list.html. (b) GET "/prompts/{name}" with optional `?version=vN` → guard unknown name (catch KeyError → raise NotFoundError(f"prompt {name}")); parse the selected version (default active_version), guard unknown version → NotFoundError; pass name, versions, active, selected, content=registry.get(name, selected) to prompt_detail.html. (c) GET "/prompts/{name}/diff" with `from`/`to` query params (aliased, since `from` is reserved — use `Query(alias="from")`/`Query(alias="to")`); strip a leading 'v' and int()-parse each (bad format or unknown name/version → NotFoundError, never 500); IGNORE any 3rd param by design; call build_line_diff(registry.get(name, x), registry.get(name, y)) and render prompt_diff.html. Register in app/routers/main.py: `from app.routers import dashboard_prompts` and `router.include_router(dashboard_prompts.router)` next to the existing `dashboard.router` include (line ~54).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.main import app; paths=[r.path for r in app.routes]; assert '/dashboard/prompts' in paths and '/dashboard/prompts/{name}' in paths and '/dashboard/prompts/{name}/diff' in paths, paths; print('routes registered')"</verify>
  <done>App imports; three routes registered under /dashboard; unknown name/version paths raise NotFoundError (→404).</done>
</task>
```

### Task 4.1 — Route tests (e2e HTML)

```xml
<task id="4.1" wave="4">
  <files>apps/api/tests/api/prompts/test_dashboard_prompts.py</files>
  <action>Mirror tests/api/agent_config/test_agent_config_dashboard.py using the session-scoped `client` fixture. Cover: (1) GET /dashboard/prompts → 200, body contains several known names (supervisor, budget) and shows a version count/active badge; (2) GET /dashboard/prompts/budget → 200, lists v1 and v2, flags the active one, shows content; (3) GET /dashboard/prompts/budget/diff?from=v1&to=v2 → 200, body shows diff markers/rows (added + removed classes present); (4) unknown name → GET /dashboard/prompts/nope → 404; unknown version → /dashboard/prompts/budget?version=v99 → 404; malformed diff param (from=vX) → 404 not 500; (5) dynamic coverage: assert the list length equals len(registry.names()) so a new prompt dir would appear without code change; (6) a 3rd diff param is ignored (from=v1&to=v2&other=v1 still 200 diffing v1↔v2).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/prompts/test_dashboard_prompts.py -x -q</verify>
  <done>All route tests green: list/detail/diff happy paths + 404s + dynamic + 2-version-only.</done>
</task>
```

## 6. Risks

- **"Rendered markdown" vs raw source** — plan shows raw `<pre>` source (no new dep, higher
  fidelity). If you want true rendered markdown, that adds a `markdown`/`markdown-it-py`
  dependency + a Jinja filter (an extra task). **Confirm at review.**
- **New-endpoint hook** — `risk-corroboration.sh` may flag new `/dashboard/prompts` routes as
  `public-contract` at commit time (they're internal HTML, `include_in_schema=False`). Known
  friction; authorize with `RISK_WARN_CATEGORIES="public-contract"` per project memory.
- **base.html is shared** (Task 2.2) — changes are additive (two nav lists only); low blast.
- **`from` is a Python keyword** — must use `Query(alias="from")` in the diff route.

## 7. Waves

| Wave | Tasks | Parallelism | Files disjoint? |
|------|-------|-------------|-----------------|
| 1 | 1.1 registry helpers · 1.2 diff helper | 2 parallel | ✅ registry.py vs core/prompt_diff.py (+ separate test files) |
| 2 | 2.1 templates · 2.2 nav | 2 parallel | ✅ 3 new prompt_*.html vs base.html |
| 3 | 3.1 router + registration | single | — |
| 4 | 4.1 route tests | single | — |

## 8. Status Log

- 2026-07-08 — Plan drafted on `feat/min-45-prompt-version-dashboard` off `v3`. Diff-rendering
  decision locked (custom table). One open item for review: raw source vs rendered markdown.
- 2026-07-08 — Raw-source decision confirmed (human). All 4 waves shipped:
  W1 `8edc6dc` (registry helpers + diff util, 10 tests), W2 `d989a3e` (templates + nav),
  W3 `12a8f07` (router + registration), W4 `2f9c86c` (12 route tests). 22 tests green on
  SQLite; ruff clean; independent correctness+intent review found no defects.
