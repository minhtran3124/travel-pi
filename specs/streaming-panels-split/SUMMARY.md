# streaming-panels-split — Summary

Lane: normal
Confidence: high
Reason: Behavior-preserving refactor of one internal module + a registry seam; only flag 8 (existing, test-covered behavior) fires — no hard gate, and the design fork was resolved with the user at intake.
Flags: existing-behavior
Affects: app/streaming (panel projections + the `panel` SSE event payload), app/tools/_base.py `panel_result`
Input-type: maintenance

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> make the plan for updating apps/api/app/streaming/panels.py with split file for each panel type. In the future we have a lot of panel, so put all into 1 place will make hard for maintain and scale

Scope-deciding answers at intake (AskUserQuestion):

- **Scope** → "Split + registry": package `app/streaming/panels/` with one file per kind; each file self-registers (kind, model, localizer) so adding a panel = adding one file, with no edit to `PanelKind` or to `panel_localizer`'s dispatch.
- **Imports** → "Giữ nguyên qua `__init__`": `from app.streaming.panels import HotelsPanel` must keep working; `app/tools/*.py` import lines are not touched.

## What changed

`app/streaming/panels.py` (593 lines, 6 panel kinds) becomes a package `app/streaming/panels/`
with `base.py` (registry + shared helpers) and one module per kind. Each module owns its
projection model, its `vi` lookup tables, and its localize function, and registers itself.
`panel_localizer.localize_panel()` keeps its signature (the mapper's import is untouched) but
dispatches through the registry instead of an `if kind == …` chain. The dead `PanelKind`
`Literal` is replaced by the registry's runtime kind list, which `panel_result()` now
validates against. No SSE payload, tool signature, or FE contract changes.

### Rationale

The user's constraint is scale ("a lot of panels"), not file size — so a mechanical split
alone would have missed the point: a panel kind currently lives in three places
(`panels.py` projection, `panel_localizer.py` `if/elif` + its `vi` tables, and the `PanelKind`
`Literal`). A per-kind module that self-registers collapses that to one place. Registry
lookup is also what makes `panel_result(kind: str, …)` — today an unvalidated free-text
string with no caller checking it — enforceable.

### Alternatives considered

- **Mechanical split only** (one file per kind + `__init__` re-export, `panel_localizer` untouched):
  smaller, near-zero-risk diff, but adding a panel would still mean editing three files. Rejected
  by the user at intake in favor of the registry.
- **Rewriting import sites to submodule paths** (`from app.streaming.panels.hotels import …`):
  wider blast radius across `app/tools/*` and tests for no real gain. Rejected at intake.

### Deviations

- **PLAN gap (task 2.1 `<files>`)** — the file set omitted `tests/streaming/test_mapper_language.py` and
  `tests/streaming/test_panel_language_e2e.py`, which reach for `panel_localizer.WEATHER_VI` /
  `panel_localizer.CATEGORY_VI` directly. The subagent correctly STOPPED at its scope boundary rather
  than widen it; the controller repointed both imports at the panel modules (import lines only — zero
  assertion edits) and re-verified. Root cause: the intake grep for panel-module coupling matched on
  `from app.streaming.panels import`, which these two files do not use — they go through
  `panel_localizer`'s namespace. Commit `5465cd6`.
- **Rule 3** — the `ruff-on-edit` hook stripped the new `get_panel` import from `app/tools/_base.py`
  twice (added before its usage existed), the known [[ruff-on-edit-strips-unused-imports]] gotcha;
  re-added once the usage landed. Same hook cosmetically re-wrapped one pre-existing line in
  `log_tool_call` — no logic touched. Commit `5465cd6`.
- **Rule 1** — deleted the dead `PanelKind = Literal[...]` (re-grepped: zero importers across `app/`
  and `tests/`). `panel_kinds()` is its live replacement. Commit `0f8b22f`.
- **Not fixed (pre-existing, left alone per surgical-changes rule):** `ruff format --check` flags
  `tests/streaming/test_flights_panel.py`, and `ruff check app tests` reports 6 errors in
  `tests/agents/test_hotel_search_intent.py`, `tests/api/expense/test_expense_repo.py`,
  `tests/memory/test_structured_namespaces.py`. All confirmed to have zero diff vs `v3` — not ours.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Baseline (pre-refactor) | `pytest tests/streaming tests/tools tests/api/agent/test_stream_events.py -q` | 0 | 188 passed — the number the refactor had to preserve |
| Panels + tools + stream (post) | `pytest tests/streaming tests/tools tests/api/agent/test_stream_events.py -q` | 0 | 196 passed = 188 baseline + 8 new `test_panel_result.py`. **Zero existing assertions edited** — the proof the SSE payload is unchanged |
| Full BE suite | `../../.venv/bin/python -m pytest -q` | 0 | 1522 passed, 55.9s |
| Lint (changed files) | `ruff check app/streaming app/tools tests/streaming tests/tools` | 0 | All checks passed |
| Format (changed files) | `ruff format --check app/streaming app/tools` | 0 | 27 files already formatted |
| Registry is live | `python -c "from app.streaming.panels import panel_kinds; print(sorted(panel_kinds()))"` | 0 | `['air_quality', 'flights', 'hotels', 'places', 'route', 'weather']` |

### Rollback

- `git revert <sha>` (pure refactor; no migration, no data change, no FE change)

### Harness-Delta

- **backlog → `/compound`.** The `blast-radius` PostToolUse hook checked every edit in this feature
  against a **stale active plan** (`specs/min-54-chat-ui-polish/PLAN.md` — a long-shipped feature),
  so it warned on every file even though all of them are listed in this feature's `PLAN.md` `<files>`
  sets. Both wave subagents flagged it independently. A hook that cries wolf on 100% of correct edits
  trains everyone to ignore it, which is exactly when it would have caught real scope creep. The
  active-plan pointer needs to resolve to the plan the work is actually running under.
