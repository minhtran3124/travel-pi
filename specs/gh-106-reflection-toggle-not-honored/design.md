---
slug: gh-106-reflection-toggle-not-honored
status: proposed
owner: Minh Tran
created: 2026-07-21
issue: GH-106
---

# GH-106 — AgentConfigCache cross-process freshness + reflection-checkbox visual bug

## 1. Motivation

GH-106 reported the reflection on/off toggle (`agent_config.enabled` on the `reflection` row →
`AgentContext.allow_reflection`, MIN-68) as a no-op. An `Explore` investigation found the DB →
cache → `AgentContext` → `make_reflection_node` path is wired correctly and all 42 related tests
pass — the toggle works today, because this API runs a single `uvicorn` process (confirmed via
`apps/api/docker-compose.yml`, no `--workers`, no Procfile/k8s manifest anywhere in the repo).

The real gap, resolved as **E001** (`specs/gh-106-reflection-toggle-not-honored/ESCALATIONS.md`,
decided 2026-07-21): `AgentConfigCache` (`app/core/agent_config_cache.py`) is a process-local,
class-level singleton. `invalidate()` (called after a dashboard save) only resets that one
process's freshness stamp — a future multi-worker/multi-replica deployment would leave sibling
processes serving stale config for up to the TTL (default 3600s). This is **future-proofing**,
not a fix for an active incident — no such deployment exists today.

While reproducing the report on the dashboard, a second, unrelated but real bug surfaced: the
"Reflection enabled" checkbox visually renders on **every** agent's edit modal (screenshots
confirm on `date_resolution` and `summarize`), not just `reflection`. This is a CSS cascade bug,
not a schema or backend gap (see §6).

## 2. Scope

Two independent, additive fixes, bundled under this spec because both touch the same dashboard
config surface and were surfaced by the same report:

- **A. Cross-process cache freshness** — replace `AgentConfigCache`'s pure time-based TTL with a
  cheap DB version-poll, so any process detects another process's config write within a short,
  bounded interval instead of up to 1h.
- **B. Reflection-checkbox visibility fix** — a one-rule CSS fix so the checkbox is actually
  hidden for non-`reflection` agents, matching the JS/backend logic that already scopes it
  correctly.

## 3. Non-goals

- No new external service dependency (Redis, pub/sub) — ruled out at brainstorm; no such
  infrastructure exists in this stack and none is planned.
- No Postgres `LISTEN/NOTIFY` — would require an engine-conditional code path (SQLite has no
  equivalent) and a new persistent-connection background task; not justified for a future-proofing
  task with no concrete multi-process deployment.
- No new DB column or migration — `AgentConfig` already inherits `updated_at` (auto-bumped by
  SQLAlchemy `onupdate` on every write) via `UUIDBase` → `TimestampMixin` (`app/db/base.py`); see
  §5.
- No change to the single-global-toggle *semantics* of reflection-enabled — it already is a
  single row (`agent_name="reflection"`) read by exactly one call site
  (`AgentConfigCache.get("reflection")` in `_resolve_context`, `app/routers/agent.py`). §6 is a
  **visual** fix only, not a data-model change.
- No per-field TTLs — the whole cached blob (`provider`/`model`/`base_url`/`temperature`/
  `max_tokens`/`enabled`) refreshes as one unit, as it does today.

## 4. Success criteria

- A config write (dashboard save or `scripts/seed_agent_config.py`) is visible to **every**
  process within one poll interval (a few seconds), not up to 1h.
- A transient DB error during a poll does not break `/agent/chat` or `/agent/stream` — the cache
  fails open to its last-known-good value and retries next interval.
- The "Reflection enabled" checkbox is not rendered (or interactable) for any agent except
  `reflection`, in both the dashboard modal (`agent_config.html`) and the legacy edit page
  (`agent_config_edit.html`).
- Existing behavior is unchanged for the current single-process deployment: same-process saves
  still take effect immediately (via `invalidate()`), all 42 existing tests continue to pass.

## 5. Architecture & data flow — cache freshness (A)

`AgentConfig` (`app/db/models/agent_config.py`) extends `UUIDBase`, which mixes in
`TimestampMixin` (`app/db/base.py`): `updated_at: Mapped[str]` with
`onupdate=_utc_now_iso` — a Python-side ISO-8601 string, bumped by SQLAlchemy on every UPDATE that
goes through the ORM. Both current write paths already go through the ORM (no raw-SQL bypass):

- `AgentConfigRepository.upsert()` (load row → set attributes → `session.commit()`) — used by
  the dashboard service and `scripts/seed_agent_config.py`.
- `app/db/seed.py::_seed_agent_config()` (`session.add(models.AgentConfig(...))`) — the startup
  seeder.

So the version marker this design needs **already exists and is already correctly maintained**;
no migration is needed.

```
Write path (either):
  AgentConfigRepository.upsert() / _seed_agent_config()
    → ORM flush bumps AgentConfig.updated_at (existing TimestampMixin behavior, unchanged)
    → AgentConfigService.update_config() still calls AgentConfigCache.invalidate() (unchanged;
      same-process instant refresh)

Read path (every process, on the next request after the poll interval elapses):
  AgentConfigCache.get(name) / .generation()
    → _maybe_refresh()
       → poll interval elapsed?
           no  → return cached value, no DB hit
           yes → AgentConfigRepository.max_updated_at()   # SELECT MAX(updated_at), one scalar
                 → unchanged from _known_updated_at?
                     yes → mark checked, return cached value (no full reload)
                     no  → reload_from_db() (existing full list_all() reload, cheap: ~5 rows)
                           → update _known_updated_at
                 → on DB error: log, keep serving current cache, mark checked (retry next
                   interval) — do not raise into the request path
```

`ISO-8601` strings (as already produced by `_utc_now_iso()`) sort correctly with a plain string
`MAX()`/`>` comparison (fixed-width, UTC, zero-padded), so this works identically on SQLite and
Postgres — no engine-specific code.

### 5.1 Components

- **`AgentConfigRepository.max_updated_at() -> str | None`** (new) — `SELECT MAX(updated_at) FROM
  agent_config`; `None` when the table is empty.
- **`AgentConfigCache`** (`app/core/agent_config_cache.py`):
  - Add `_known_updated_at: str | None = None`.
  - `_maybe_refresh()`: replace "reload unconditionally past TTL" with "poll `max_updated_at()`
    past the interval; reload only on a value change." Wrap the poll + reload in `try/except`;
    on failure, `logger.error(...)` and re-stamp `_loaded_at` so the next attempt is one interval
    away (no request-path exception, no retry storm).
  - `invalidate()` — unchanged semantics (forces the next read in *this* process to re-poll
    immediately).
  - `clear()` — also reset `_known_updated_at` (tests).
- **Settings** (`app/core/config.py`): rename `agent_config_cache_ttl_seconds` →
  `agent_config_poll_interval_seconds` (2 call sites total: the setting definition and
  `AgentConfigCache.configure()` in `app/core/lifespan.py` — confirmed via repo-wide grep, no
  other references). Lower the default from `3600` to a few seconds (exact value picked at plan
  time, e.g. `3`). Update the docstring/comment on `AgentConfigCache` (currently says "take effect
  within ~1h") to describe the new poll-then-conditionally-reload behavior.

### 5.2 Error handling

Today, an unhandled reload failure would surface at most once per TTL window (1h) — rare enough
that it was never handled. Shrinking the effective check interval to a few seconds makes any DB
hiccup during that window hit far more requests unless handled. This design adds: catch
exceptions from `max_updated_at()` and `reload_from_db()` in `_maybe_refresh()`, log at `error`
level (`logger.error(f"[AgentConfigCache] ...: {e}")`, per project convention), keep serving the
last-known-good in-memory cache, and re-stamp so the next attempt waits one full interval (avoids
hammering a struggling DB every request).

## 6. Reflection-checkbox visibility fix (B)

Root cause (confirmed via git history + directly inspecting the running Docker container's mounted
file, which matches the host — this is not a stale-container issue): the checkbox's wrapper
(`<label class="am-field am-check" id="am-enabled-field" hidden>` in `agent_config.html`) is
correctly toggled by JS (`enField.hidden = !isRefl`, `agent_config.html:403`) for every agent
except `reflection`. But `.am-field { display: flex; ... }` (`agent_config.html:315`) is an author
CSS rule that overrides the `hidden` attribute's implicit `display: none` (a browser default-
stylesheet rule any author `display` rule takes precedence over) — so the field stays visually
flex-displayed regardless of the `hidden` attribute. `disabled` on the inner `<input>`s (already
present, `agent_config.html:404-405`) does still work — a save on a non-`reflection` agent never
submits `enabled` — so this is a **visual-only** bug; no data-integrity issue.

Fix: add an ID-scoped rule (specificity beats the `.am-field` class rule without `!important`):

```css
#am-enabled-field[hidden] { display: none; }
```

Apply the same fix to `agent_config_edit.html` if its "Reflection enabled" block has the same
`.am-field`-class-plus-`hidden` shape (verify at implementation time — that template already
gates the block with `{% if agent_name == 'reflection' %}` server-side rather than client-side
`hidden`/`disabled`, so it may not need the fix; confirm during implementation rather than assume).

## 7. Testing

| Area | Check |
|---|---|
| Cache poll | Same `max_updated_at()` across two reads within the interval → no `reload_from_db()` call (mock/spy). |
| Cache reload | Changed `max_updated_at()` → `reload_from_db()` called, `_known_updated_at` updated, `generation` bumps if data changed. |
| Cache error handling | `max_updated_at()` raises → cache keeps serving last-known value, no exception propagates, `logger.error` called. |
| Existing suite | `tests/agents/test_agent_context.py`, `tests/agents/test_depth_toggles.py`, `tests/api/agent_config/test_agent_config_dashboard.py` — all still pass unmodified (behavior contract unchanged for single-process case). |
| Full-path integration (closes the gap the Explore investigation flagged) | Dashboard POST disabling reflection → a fresh `AgentConfigCache`-equivalent read (simulating a second process reading the same DB) sees `enabled=False` within one poll interval, without calling `invalidate()` directly. |
| CSS fix | Automated: a headless-browser check that asserts the computed style / element visibility for `#am-enabled-field` is hidden on a non-`reflection` agent's modal (per `plan-format.md` Guardrail 2, `<verify>` must be an automated command, not "open browser and check" — see repo's existing Node-24 + playwright-core workaround noted in project memory for the MCP Playwright issue). |

### 7.1 `tests/core/test_agent_config_cache.py` must be updated, not just added to

This file tests `AgentConfigCache` directly and is tightly coupled to the mechanism this design
replaces. Two tests assert the **old** unconditional-TTL-reload behavior and will break under the
new design if left as-is:

- `test_get_reloads_from_db_when_stale` and `test_get_skips_reload_when_fresh` both call
  `AgentConfigCache.configure("FACTORY", ttl_seconds=3600)` — a bare string standing in for a
  session factory — then monkeypatch `reload_from_db` directly and assert it was/wasn't called
  based on `_loaded_at` alone. Under the new design, `_maybe_refresh()` calls
  `AgentConfigRepository.max_updated_at()` *before* deciding whether to reload — which needs a
  real session factory, not the string `"FACTORY"` — so these two tests would fail (or crash) as
  written; they must be rewritten to also mock/stub `max_updated_at()` (e.g. monkeypatch
  `AgentConfigRepository.max_updated_at` to return a controlled value, and assert
  `reload_from_db` is called only when that value changes across two `.get()` calls).
- `test_no_reload_without_configure`, `test_invalidate_forces_next_read_to_reload`,
  `test_reload_from_db_reflects_an_upsert`, and the `sync_from_cache`/`generation` tests exercise
  behavior this design leaves unchanged and should keep passing unmodified — confirm at
  implementation time rather than assume.

The "42 tests" figure in §4 refers to the tests found by the earlier Explore investigation and
does **not** include this file; treat it as a required, separate update, not optional cleanup.

## 8. Risks

- **Rule-4 hard gate: "replacing a service/pattern"** — `AgentConfigCache`'s invalidation model
  changes from pure TTL to version-poll. Mitigated by: no new infra, no new external dependency,
  behavior is a strict improvement (tighter bound) for the only deployment topology that exists
  today, and the change is additive/reversible (`git revert`).
  - **Rollback:** `git revert <sha>` (all pieces are code + a settings rename, no migration to
    reverse).
- **Settings rename** (`agent_config_cache_ttl_seconds` → `agent_config_poll_interval_seconds`) —
  only 2 in-repo references (confirmed via grep); no `.env.example`/docs currently reference the
  old name. Low blast radius, but flag in the PLAN so nothing external (deploy scripts, ops
  runbooks outside this repo) is missed.
- **Poll frequency vs. DB load** — negligible at this table's size (~5-9 rows), even at a
  few-second interval; revisit if `agent_config` ever grows to hold materially more rows.
- **CSS fix scope** — confirm at implementation time whether `agent_config_edit.html` needs the
  same fix or is already correctly gated server-side (§6); don't apply a speculative fix to a
  template that doesn't have the bug.
- **Scope bundling (A + B in one spec)** — Fix A trips the Rule-4 hard gate and correctly carries
  the full high-risk chain (worktree, full plan ceremony); Fix B is a one-line, mechanically
  unrelated CSS rule. Bundling them under one spec is reasonable (same report, same dashboard
  surface, surfaced together), but the PLAN.md should structure B as its own small, independently
  verifiable task/wave so its ceremony isn't inflated by A's lane — it does not need worktree
  isolation or the same review depth on its own merits.
- **Redundant reload on first poll after process start (non-blocking)** — `lifespan.py`'s
  startup-time direct `reload_from_db()` call doesn't set `_known_updated_at` (only the new poll
  path in `_maybe_refresh()` does), so the first poll after startup will always see an apparent
  "change" and trigger one extra reload. Harmless given the table's size, but worth a one-line
  comment in the implementation so a reviewer doesn't mistake it for a bug.

## 9. Status log

- 2026-07-21 — GH-106 intake: `Explore` investigation found no code bug in the single-process
  case; escalated (E001) on ambiguous direction (SUMMARY.md, ESCALATIONS.md).
- 2026-07-21 — E001 resolved: fix cross-process `AgentConfigCache` invalidation (decision B); lane
  bumped to high-risk (Rule-4: replacing a service/pattern).
- 2026-07-21 — Brainstorm: ruled out Redis/pub-sub (new external dep) and Postgres `LISTEN/NOTIFY`
  (engine-specific, more moving parts) in favor of a version-poll using the already-existing
  `AgentConfig.updated_at` (no migration needed) — confirmed both write paths already bump it via
  the ORM. User flagged a second, unrelated bug during dashboard verification (checkbox visible on
  every agent); root-caused to a CSS cascade issue (`.am-field { display: flex }` overriding
  `hidden`), folded into this spec as §6.
