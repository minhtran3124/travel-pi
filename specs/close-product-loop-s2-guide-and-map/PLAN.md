---
slug: close-product-loop-s2-guide-and-map
status: active
owner: Minh Tran
created: 2026-09-09
---

# Destination guide, trip map, and a visa tool for the assistant

## 1. Motivation

Slice 2 of `specs/close-product-loop/design.md`. Two screens over APIs that already exist, plus one
addition the user asked for at intake: bind visa to the assistant.

The visa gap is the sharpest part. `GET /visa` has worked all along, but no agent tool wraps it, so
the concierge answers visa questions out of the RAG index and — when that misses — currently says so
in as many words. `app/prompts/concierge/v11.md:106-109` reads:

> If the tool returns `count: 0`, fall back to `get_local_tips` … **for visa questions there is no
> other source, so say plainly you don't have that** …

There is a source. It is one route away. That sentence stops being true the moment the tool exists,
which is why the prompt change here is required rather than cosmetic.

Intake: `specs/close-product-loop-s2-guide-and-map/SUMMARY.md` (lane `normal`; both open questions
decided by the user before planning).

## 2. Non-goals

- **No routing lines on the trip map.** Markers only, per design §S2.
- **No second map.** The chat Route panel and the new tab share one component — the user's decision,
  and S1 showed the extraction is safe when the panel's tests pin its behaviour.
- No new HTTP route, no schema change, no migration. Every endpoint this needs already ships.
- No change to how `search_travel_knowledge` works. The new tool sits beside it; the prompt says
  which to reach for.
- No visa tool on `planner`. Planner shapes trips; concierge owns destination knowledge.
- No web booking anything. The pages stay browse-only.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | The assistant has a visa tool, bound to concierge and nowhere else | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_visa_tools.py -q` | exit 0 |
| SC-2 | An unknown destination is answered, not raised as an error | `cd apps/api && ../../.venv/bin/python -m pytest "tests/tools/test_visa_tools.py::test_unknown_destination_returns_not_found" -q` | exit 0 |
| SC-3 | The registry still assembles and every tool name stays unique | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py tests/mcp -q -p no:randomly` | exit 0 |
| SC-4 | Concierge v12 loads and no longer claims visa has no source | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts/test_prompt_registry_helpers.py -q -p no:randomly` | exit 0 |
| SC-5 | The chat Route panel behaves exactly as before the map moved | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/panel/RoutePanel.test.tsx` | exit 0 |
| SC-6 | `/guide/[city]` renders visa, tips and climate, and the disclaimer verbatim | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/app/guide/page.test.tsx` | exit 0 |
| SC-7 | The trip page has a Map tab that renders its markers | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/map/MapTab.test.tsx` | exit 0 |
| SC-8 | Every new string exists in both locales | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/messages.parity.test.ts` | exit 0 |
| SC-9 | The frontend typechecks | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit` | exit 0 |
| SC-10 | Backend lint is clean | `cd apps/api && ../../.venv/bin/ruff check app` | exit 0 |
| SC-11 | Frontend lint is clean | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec eslint .` | exit 0 |
| SC-12 | The concierge prompt names the visa tool and no longer denies having a source | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_concierge_prompt.py -q` | exit 0 |

Checks name files, not directories, where a directory would drag in known-failing neighbours: all of
`tests/tools` pulls in two `test_routing_tools.py` offline-estimate tests that fail whenever the
network is up, and all of `tests/api/prompts` pulls in fourteen dashboard tests that 401 from a local
`.env`. Both predate this slice.

## Global Constraints

- **Worktree.** All work happens in `.worktrees/feat/close-product-loop-s2-guide-and-map`, branched
  from `main` at `4cb8f10`. The main checkout belongs to another session's branch — never touch it.
  `.venv` is a symlink to the main checkout's, so `../../.venv/bin/python` resolves as documented.
- **Copy the sibling, do not invent.** `app/tools/tip_tools.py` is the shape for the visa tool: a
  read-only lookup, its own `session_scope`, `AppError` mapped through `tool_error`, `dump()` on the
  way out, no side-panel artifact, and a `VISA_TOOLS` list at the bottom.
- **The disclaimer is not the model's to reword.** `VisaResponse.disclaimer` must reach the traveller
  intact — the tool returns it and the prompt says to pass it through.
- **`found: false` is an answer, not an error.** The endpoint returns it for an unknown destination
  and the tool must do the same. Do not raise.
- **A new tool widens the MCP surface.** Everything outside `_DESTRUCTIVE` is auto-exposed as
  read-only. That is fine for visa; do not add it to `_DESTRUCTIVE`, and do not touch `app/mcp/`.
- **Do not weaken the panel.** The map extraction must keep `RoutePanel`'s single `data` prop, its
  lazy maplibre import, and everything its two tests assert.
- **i18n.** Every new string lands in both `messages/en.json` and `messages/vi.json` in the same
  edit. Never call `t.has`.
- Never use `max-w-md`; the spacing scale shadows the container scale. Use `max-w-[28rem]`.
- The ruff-on-edit hook deletes an import added before its first use — add an import and its first
  usage in the same edit.
- A prompt edit does not reach a running server: `docker exec api-api-1 touch app/main.py`. Note the
  container mounts the **main checkout**, not this worktree, so a live check needs that checkout on
  this branch — leave live checks to UAT.
- **Never run the whole suite in a task Verify.** That belongs to `finishing-a-development-branch`.

## 4. Tasks

### Task 1.1 — A visa tool on the concierge (wave 1)

- **Files:** apps/api/app/tools/visa_tools.py, apps/api/app/tools/registry.py, apps/api/tests/tools/test_visa_tools.py
- **Action:** Write `tests/tools/test_visa_tools.py` first: a known destination returns the entry
  guidance with the `disclaimer` present; an unknown one comes back with `found: false` and raises
  nothing — name that test `test_unknown_destination_returns_not_found`, the criteria select it by
  node id; passing neither `city` nor `country` raises `ToolException`, matching how the route
  answers 422 and how `get_local_tips` guards the same case.
  Then write `visa_tools.py` modelled line for line on `tip_tools.py`: an args model with optional
  `city` and `country` (fuzzy, city wins when both are given — the route's own semantics), a `@tool`
  that opens `session_scope`, calls `VisaService.get_visa`, maps `AppError` through `tool_error`, and
  ends with `VISA_TOOLS = [get_visa]`. Bind `VISA_TOOLS` into the `concierge` domain in
  `registry.py` beside `TIP_TOOLS`, and nowhere else.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_visa_tools.py tests/tools/test_tool_registry.py tests/mcp -q -p no:randomly`
- **Done:** The tool answers a known and an unknown destination, refuses an empty query, appears in
  the concierge domain and in no other, and the registry and MCP tests still pass.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes the existing visa service and tool registry. Produces `apps/api/app/tools/visa_tools.py` and a `VISA_TOOLS` binding in `apps/api/app/tools/registry.py`.

### Task 1.2 — Lift the map out of the chat Route panel (wave 1)

- **Files:** apps/web/src/components/map/TripMap.tsx, apps/web/src/components/chat/panel/RoutePanel.tsx
- **Action:** Move the maplibre setup out of `RoutePanel.tsx` into `src/components/map/TripMap.tsx`,
  a presentational component taking the markers to draw and nothing else, and have the panel render
  it. Keep the lazy `await import("maplibre-gl")` — the map must stay off the initial bundle. Keep
  `RoutePanel`'s single `data` prop and everything its two tests assert; this task changes no
  behaviour, only where the code lives.
  Design the props for both callers now, so Task 3.1 does not have to reshape them: a list of
  markers with a position, a label, and an optional colour, plus an optional route line the panel
  passes and the tab does not.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/panel/RoutePanel.test.tsx`
- **Done:** `TripMap` exists and is the only place maplibre is constructed; `RoutePanel` renders it
  and both of its tests pass unchanged.
- **Criteria:** SC-5
- **Interfaces:** Consumes the existing panel data shape. Produces `apps/web/src/components/map/TripMap.tsx`.

### Task 2.1 — Tell the concierge the visa source exists (wave 2)

- **Files:** apps/api/app/prompts/concierge/v12.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/prompts/test_concierge_prompt.py
- **Action:** Copy `concierge/v11.md` to `v12.md`. Rewrite the "Visa & local advice" section so the
  assistant reaches for `get_visa` when the traveller asks about entry requirements for a named
  destination, and keeps `search_travel_knowledge` for free-text or nuanced questions the structured
  lookup cannot answer. **Delete the claim that there is no other source for visa questions**
  (`v11.md:106-109`) — it is now false. Keep the guidance-not-a-ruling framing and the instruction to
  pass the disclaimer through, both of which matter more now that the answer is structured. Change
  nothing else in the prompt. Point `active.yaml` at `concierge: 12` and add a `CHANGELOG.md` entry
  in the style of the entries already at the top.
  Then pin the change in `tests/prompts/test_concierge_prompt.py`, which today asserts only that the
  prompt mentions `exclude_names`. Add two assertions against the active concierge prompt: it names
  `get_visa`, and it does **not** contain "no other source". Without them SC-4 proves only that some
  prompt loaded — it cannot tell v11 from v12.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts/test_prompt_registry_helpers.py -q -p no:randomly`
- **Done:** The prompt tests pass with the two new assertions, so v12 both names the tool and has
  dropped the "no other source" claim; `active.yaml` resolves to 12.
- **Criteria:** SC-4, SC-12
- **Interfaces:** Consumes the tool from Task 1.1. Produces `apps/api/app/prompts/concierge/v12.md`.

### Task 2.2 — The destination guide page (wave 2)

- **Files:** apps/web/src/app/guide/[city]/page.tsx, apps/web/src/app/guide/page.test.tsx, apps/web/src/lib/query/guide.ts, apps/web/src/lib/api/keys.ts, apps/web/src/components/trips/TripHeader.tsx, apps/web/src/app/places/page.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Build `/guide/[city]` as a client page with three sections — visa from `GET /visa`,
  tips from `GET /tips`, climate from `GET /destinations/climate?city=`. Follow the page conventions
  the codebase already uses: TanStack Query hooks in `src/lib/query/`, keys from
  `src/lib/api/keys.ts`, and the spinner / error / empty / content ladder from
  `src/app/bookings/page.tsx`. **Render the visa `disclaimer` verbatim** — do not summarise or
  restyle it away. Each section fails independently: one endpoint erroring must not blank the other
  two. Add entry points from the trip header's destination city and from `/places`.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/app/guide/page.test.tsx src/messages.parity.test.ts`
- **Done:** The page renders all three sections with the disclaimer verbatim, one failing section
  leaves the others intact, both entry points link to it, and the locale files stay at parity.
- **Criteria:** SC-6, SC-8
- **Interfaces:** Consumes the three existing endpoints. Produces `apps/web/src/app/guide/[city]/page.tsx` and `apps/web/src/lib/query/guide.ts`.

### Task 3.1 — The trip Map tab (wave 3)

- **Files:** apps/web/src/components/trips/map/MapTab.tsx, apps/web/src/components/trips/map/MapTab.test.tsx, apps/web/src/app/trips/[tripId]/page.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Add a `MapTab({ tripId })` following the tab contract in
  `src/components/trips/expenses/ExpensesTab.tsx`: a client component with its own translations and
  its own spinner / error / empty ladder inside a `Card`. It renders `TripMap` from Task 1.2 with
  markers for the trip's saved places (`/trips/{id}/places`) and for itinerary items carrying a
  `place_id`, coloured by day, and shows a short summary when a marker is clicked. No route lines.
  Register it in the `Tab[]` list on the trip page. That list already holds five tabs and this makes
  six; whether the row still reads at a narrow width is a browser question, so leave it to UAT and
  say in your report that it is unmeasured.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/map/MapTab.test.tsx src/messages.parity.test.ts`
- **Done:** The trip page shows a Map tab that plots the trip's places and dated itinerary items,
  colours them by day, and summarises a clicked marker; the locale files stay at parity.
- **Criteria:** SC-7, SC-8
- **Interfaces:** Consumes the shared map component from Task 1.2. Produces `apps/web/src/components/trips/map/MapTab.tsx`.

### Task 4.1 — The closing gates (wave 4)

- **Files:** apps/api/app/prompts/CHANGELOG.md
- **Action:** Run the project-wide typechecker and both linters as the final gate. Expect no edits —
  each task fixes its own. If a tool reports something, fix it in the file the owning task declared
  and note the deviation there rather than editing outside this task's Files set — that reopens the
  owning task rather than widening this one, because the fix would otherwise land outside the Files
  this task declares and trip the blast-radius check. Correct the changelog entry from Task 2.1 if
  the final shape of v12 drifted from what it described.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit`
- **Done:** `tsc --noEmit` exits 0. `pnpm exec eslint .` (0 errors; the one pre-existing
  `useAgentStream.ts` warning is expected) and `ruff check app` are run separately and each exit
  code is recorded in the report — they carry their own criteria rows rather than this task's
  Verify, which stays a single command.
- **Criteria:** SC-9, SC-10, SC-11
- **Interfaces:** Consumes the finished slice. Produces the final `apps/api/app/prompts/CHANGELOG.md` entry.

## 5. Risks

- **Two overlapping visa answers.** The concierge will hold both `get_visa` and
  `search_travel_knowledge`, and only the prompt separates them. If v12 is vague the model will pick
  unpredictably. This is why Task 2.1 exists and why it must delete the old sentence rather than
  append to it.
- **The map extraction is the one change that can break something users have today.** `RoutePanel`
  has only two tests, which is thin cover for a component that builds a map imperatively. Treat a
  green run as necessary, not sufficient, and look at the panel in a browser during UAT.
- **Six tabs.** The row was already at five. Nobody has measured it below 1280px.
- **The dev container mounts the main checkout, not this worktree.** Any live check of the prompt or
  the tool needs that checkout on this branch, which another session currently owns. UAT has to wait
  for it, or run from the worktree with its own server.
- The two `tests/tools/test_routing_tools.py` offline-estimate failures predate this slice and fail
  whenever the network is up. The Verify commands are scoped around them on purpose.

## 6. Status Log

| Date | Event |
|---|---|
| 2026-09-09 | Plan written from the intake SUMMARY, in a worktree branched from `main` at `4cb8f10`. Status `proposed`. |
| 2026-09-09 | Re-review: approved. Two wording gaps closed in Task 4.1 — its Done no longer claims what its single-command Verify cannot decide, and its Action says a lint fix reopens the owning task rather than widening this one. |
| 2026-09-09 | Independent review: three issues fixed. Task 2.2 required entry points in files it had not declared; SC-4 could not tell v12 from v11, so Task 2.1 now pins two assertions in the concierge prompt test; SC-9 chained two commands and is split into SC-9, SC-11 and a wave-4 gate task. Line citation corrected to `v11.md:106-109`. Measured: tsc 1.8s, eslint 4.4s. |
