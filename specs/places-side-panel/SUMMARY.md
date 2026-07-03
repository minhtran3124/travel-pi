<!--
  Canonical SUMMARY.md shape. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
-->

# places-side-panel — Summary

Lane: normal
Confidence: high
Reason: One flag fired — public-contract (new `"places"` panel artifact riding the existing SSE `panel` event + a new FE renderer). Purely additive: no auth/authz, no schema/migration, no new external provider, no removal of existing behavior. Not ambiguous — this is the exact deferred item recorded in `specs/agent-side-panel/SUMMARY.md` Deviations ("Places/Weather deferred to their tool conversions"), and research confirmed the frontend already reserves the `"places"` `PanelKind` + label, only missing the renderer + backend artifact.
Flags: public-contract
Affects: `app/tools/place_tools.py` (search_places tool), `app/streaming/panels.py` (new `PlacesPanel` projection), `apps/web/src/lib/stream/panel.ts` (new `PlacesPanelData`), `apps/web/src/components/chat/panel/registry.ts` (new renderer registration)
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane.

### Intent

> hiện tại là chatbot trả lời về câu hỏi tìm kiếm khách sạn hoặc places thì mới trả về text, update thêm để trả về side panel giong nhu tool khac

(Translation for the record: "Currently the chatbot only returns text when answering hotel-search or places questions; add an update so it also returns a side panel like other tools already do.")

**Scope correction from research:** `search_hotels` is already panel-capable (`app/tools/hotel_tools.py`, kind `"hotels"`) — the premise that hotel-search is text-only is stale. The actual gap is `search_places` only: it's a plain `@tool` with no `response_format="content_and_artifact"`, so it never emits the `panel` SSE event, and the frontend has no `PlacesPanel` component registered even though `PanelKind` and `PANEL_LABELS` already reserve `"places"` as forward-compat. Scope for the resulting PLAN.md is: make `search_places` panel-capable, following the established `content_and_artifact` + `panel_result()` convention (already proven by hotels/flights/route/weather).

## What changed

`search_places` (`apps/api/app/tools/place_tools.py`) is now panel-capable: converted to
`@tool(response_format="content_and_artifact")`, returning a short model-facing summary plus a
`kind="places"` side-panel artifact on matches (built by a new `PlacesPanel`/`PlacesPanelPlace`
projection in `app/streaming/panels.py`), or a message and no panel on empty results — mirroring
the already-shipped `search_hotels` pattern exactly. The frontend gained a matching
`PlacesPanel.tsx` renderer (compact expandable place list, `is_recommended` picks ringed in lime)
registered under `PANEL_RENDERERS["places"]`, plus the `PlacesPanelData`/`PlacesPanelPlace` TS
types in `panel.ts`. No SSE/mapper/registry-shell changes were needed — both were already generic
over panel `kind`. Two real bugs surfaced by the final adversarial correctness review were fixed:
the summary/panel header echoed the raw (pre-fuzzy-match) city/category input instead of the
canonical resolved value, and a CSS `capitalize` class up-cased the word "reviews" in the Rating
detail.

### Rationale

Mirror an already-proven mechanism (`content_and_artifact` + `panel_result()`) rather than
inventing anything new — `search_hotels`/`search_flights`/`get_route`/`get_weather` all use the
identical shape, and the frontend had already reserved the `"places"` `PanelKind` + label as
forward-compat when the original `agent-side-panel` initiative explicitly deferred the places
projection "to its tool conversion." This is that deferred conversion, not a new design.

### Alternatives considered

- none — this is a mirror of an established, already-reviewed pattern, not a design fork.

### Deviations

- Rule 3 — Re-added two imports (`Place` in `panels.py`, `PlacesPanel`+`panel_result` in `place_tools.py`) that the `ruff-on-edit` hook stripped mid-edit (added before first use). Commit `916fcd6`.
- Rule 3 — Commit blocked by `risk-corroboration.sh`'s `weakening-validation` gate (test rewrite deletes old `assert isinstance(out, list)` lines); downgraded via `RISK_WARN_CATEGORIES="weakening-validation"` — confirmed benign (test-invocation-style only, no production validation touched) by both spec and code-quality review. Commit `916fcd6`.
- Rule 3 — Commit blocked by `risk-corroboration.sh`'s `data-loss/migration` gate — a false positive from the hook's regex matching the Tailwind `truncate` CSS class (used identically in sibling panels). Downgraded via `RISK_WARN_CATEGORIES="data-loss/migration"`; confirmed by code-quality review (`grep` for real schema/migration/delete signals in the diff found none). Commit `f40a4fb`.
- Rule 1 — Final adversarial correctness review found `search_places`'s summary/panel header echoed the raw (pre-fuzzy-match) `city`/`category` input instead of the canonical resolved value (e.g. "danang" instead of "Da Nang") — mirrors `search_hotels`'s `results[0].city` pattern now. `apps/api/app/tools/place_tools.py`. Commit `8abccc1`.
- Rule 1 — Same review found a CSS `capitalize` class on `PlacesPanel.tsx`'s shared `Detail` component up-cased the literal word "reviews" inside the composite Rating string; moved `capitalize` to the Category call site only (matches `HotelsPanel.tsx`'s transform-free `Detail`). `apps/web/src/components/chat/panel/PlacesPanel.tsx`. Commit `4d7953e`.

### Advisory Findings

<!-- Score < 80 threshold — not blocking, recorded per correctness-review's residual-work gate. -->

- **P2 / Rule 4 — `search_places` has no result cap.** Unlike `search_hotels` (caps at 12), `search_places` with broad/no filters can return the entire seeded set (up to ~500 places, ~197 for a single city like Da Nang) — all projected into the `PlacesPanel` artifact, persisted on the LangGraph checkpoint, and rendered as one row per place in the FE drawer. Scored 75/100 (real but pre-existing unboundedness in `PlaceService.search_places`, newly exposed via the panel path rather than newly introduced). Not fixed in this pass — capping/pagination is a design decision (Rule 4: changes tool output shape / contract), not a mechanical fix. Follow-up: cap `PlacesPanel.from_places` similarly to `HotelsPanel`'s top-12, or add FE virtualization.
- **Dropped (score 0, false positive):** `search_places` catches only `AppError`, not `ValueError` (parity gap vs. `search_hotels`). Traced `PlaceService.search_places` → `resolve_city`/`resolve_category` → `best_match`/`fuzzy_filter` → repository `.search()` — no reachable `ValueError` source exists in this path (unlike hotels' date parsing). No action needed.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Task 1.1 tests | `pytest tests/streaming/test_places_panel.py tests/tools/test_place_tools.py -q` | 0 | 19 passed (independently re-run) |
| Full backend suite | `DATABASE_URL="sqlite:////tmp/verify_places_side_panel.db" pytest tests/ -q` | 1 | 1241 passed, 8 failed — same 8 pre-existing/env-driven failures (LLM config defaults + routing offline-estimate) confirmed present before this change too; unrelated |
| Lint (changed files) | `ruff check app/streaming/panels.py app/tools/place_tools.py tests/streaming/test_places_panel.py tests/tools/test_place_tools.py` | 0 | All checks passed |
| Task 2.1 tests | `pnpm vitest run src/components/chat/panel` | 0 | 20 passed (7 files, independently re-run) |
| FE typecheck | `npx tsc --noEmit` | 0 | clean |
| FE lint | `pnpm lint` | 0 | clean |

### Intent Findings

- None. Final intent review (fresh reviewer, blind to PLAN.md, oracle = this file's `### Intent`
  block) traced the full artifact→SSE→registry→renderer chain and found no gap/drift/excess.
  Verified independently that hotels' pre-existing panel-capability (the scope-correction) holds
  and that no unrelated files (incl. `hotel_tools.py`) were touched. ✅ No intent divergence.

### Rollback

- `git revert 4d7953e 8abccc1 f40a4fb 916fcd6` (or revert the branch merge). Purely additive —
  no migrations, no schema changes, no data changes.

### Harness-Delta

- backlog — `.claude/hooks/render-plan-on-write.sh` looks for the render script at
  `$REPO_DIR/skills/visual-planner/render_plan.py`, but it actually lives at
  `$REPO_DIR/.claude/skills/visual-planner/render_plan.py` (missing `.claude/` prefix). The hook
  fails the `[ -f "$RENDER" ]` check and silently exits 0 — no PLAN.html is auto-rendered and no
  warning is shown. Worked around this run by rendering manually
  (`python3 .claude/skills/visual-planner/render_plan.py specs/<slug>/PLAN.md`). → `/compound`.
- backlog — `CLAUDE.md`/`Makefile` describe `make test` (apps/api) as "full suite on SQLite
  (fast, zero-config)", but `apps/api/.env` commits `DATABASE_URL=postgresql+psycopg://...:5433/...`
  and neither `make test` nor a bare `pytest` invocation overrides it — only HTTP-level tests using
  the `client`/`TestClient` fixture hit this (their app's lifespan reads real `Settings.database_url`
  before the `get_session` dependency override applies), causing 51 failed + 538 errors whenever the
  local Postgres dev container isn't running. The zero-config claim only holds with an explicit
  `DATABASE_URL=sqlite:///...` override, which isn't documented in `CLAUDE.md`'s `make test` line.
  Cost real time in this session (~4 min lost to a false "baseline failing" alarm before finding the
  correct override). → `/compound`.
