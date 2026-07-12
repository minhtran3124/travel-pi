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

<!-- filled at execution -->

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

<!-- filled at execution -->

- none

### Verify

<!-- filled at execution — one row per check actually RUN -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |

### Rollback

- `git revert <sha>` (pure refactor; no migration, no data change)

### Harness-Delta

- none
