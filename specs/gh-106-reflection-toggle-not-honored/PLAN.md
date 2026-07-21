---
slug: gh-106-reflection-toggle-not-honored
status: active
owner: Minh Tran
created: 2026-07-21
---

# GH-106 — AgentConfigCache cross-process freshness + reflection-checkbox CSS fix

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to
> implement this plan task-by-task.

**Goal:** (A) Replace `AgentConfigCache`'s pure-TTL refresh with a cheap DB version-poll (using
the already-existing `AgentConfig.updated_at` column — no migration) so a config write is visible
to every process within a few seconds instead of up to 1h. (B) Fix a CSS bug where the "Reflection
enabled" checkbox visually renders on every agent's dashboard modal instead of only `reflection`.

**Architecture:** `AgentConfigRepository.max_updated_at()` (new, cheap scalar query) →
`AgentConfigCache._maybe_refresh()` (poll first, `reload_from_db()` only on a change) →
unchanged downstream (`AgentContext.allow_reflection`, `make_reflection_node`). Settings:
`agent_config_cache_ttl_seconds` renamed to `agent_config_poll_interval_seconds` (2 call sites),
default lowered `3600` → `5`. Fix B is one CSS rule in `agent_config.html`, mechanically unrelated
to Fix A — kept as its own task so its ceremony doesn't inherit A's.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (existing), Jinja2 (existing) — no new dependency.

**Lane:** high-risk (Rule-4: "replacing a service/pattern" — `AgentConfigCache`'s invalidation
model changes from pure TTL to version-poll). See `specs/gh-106-reflection-toggle-not-honored/{SUMMARY.md,ESCALATIONS.md,design.md}`.

**Plan-time decisions (locked):**

- **Poll interval default: `5` seconds** (design.md left this as "e.g. 3, picked at plan time").
  Satisfies the brainstorm's "near-instant (seconds)" requirement without excessive DB chatter.
- **Cross-process integration test placed in `tests/core/test_agent_config_cache.py`, not the
  dashboard HTTP test file.** design.md §7 sketched this as "a fresh `AgentConfigCache`-equivalent
  read ... simulating a second process," which is most precisely modeled by writing directly via
  `AgentConfigRepository` (bypassing `AgentConfigCache.invalidate()` entirely, since that models
  *this* process's own write, not another process's) and asserting the cache under test still
  picks up the change via the poll — a repo+cache-level test, not an HTTP-level one.
- **CSS fix `<verify>` is a static text assertion on the rendered template**, not a real
  headless-browser render. No Playwright/Selenium exists anywhere in this repo's test suite today
  (confirmed via grep); adding one for a single CSS rule is disproportionate. The assertion checks
  that the `#am-enabled-field[hidden]` override rule is present in the rendered HTML — automatable
  and <60s, but does not execute real CSS cascade computation. A manual screenshot check (as done
  during brainstorming) remains the way to *confirm* the cascade behavior; it is not the CI gate.
  Flagged as a residual risk below, not silently resolved.
- **`AgentConfigRepository.max_updated_at()` and the cache's poll call are module-level functions**
  (`max_updated_at(session_factory)` in `agent_config_cache.py`, mirroring the existing
  `reload_from_db(session_factory)` free function) — keeps the same monkeypatch-in-tests pattern
  the file already uses, rather than instantiating a repo inline inside `_maybe_refresh`.

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `apps/api/app/repositories/agent_config.py` | modify | Add `max_updated_at()` — one scalar query |
| `apps/api/tests/api/agent_config/test_agent_config_repo.py` | modify | Test `max_updated_at()` |
| `apps/api/app/core/config.py` | modify | Rename + lower default: `agent_config_cache_ttl_seconds` → `agent_config_poll_interval_seconds` (5) |
| `apps/api/app/core/lifespan.py` | modify | Use the renamed setting name |
| `apps/api/app/templates/agent_config.html` | modify | Add `#am-enabled-field[hidden] { display: none; }` |
| `apps/api/tests/api/agent_config/test_agent_config_dashboard.py` | modify | Add the CSS-rule-presence assertion |
| `apps/api/app/core/agent_config_cache.py` | modify | Poll-then-conditionally-reload logic + fail-open error handling |
| `apps/api/tests/core/test_agent_config_cache.py` | modify | Rewrite the 2 tests coupled to the old unconditional-reload behavior; add poll/reload/error-handling/cross-process tests |

All commands below run from `apps/api/`. Test runner: `../../.venv/bin/python -m pytest`.

---

## Chunk 1: Cross-process cache freshness + CSS fix

### Task 1.1 — `AgentConfigRepository.max_updated_at()` (wave 1)

- **Files:** `apps/api/app/repositories/agent_config.py`, `apps/api/tests/api/agent_config/test_agent_config_repo.py`
- **Action:** Add a cheap freshness probe to the repository: a single `SELECT MAX(updated_at)`
  scalar query, used by the cache's poll (Task 3.1) instead of a full `list_all()`.

  Test-first — append to `apps/api/tests/api/agent_config/test_agent_config_repo.py`:

  ```python
  def test_max_updated_at_returns_none_when_empty(repo):
      assert repo.max_updated_at() is None


  def test_max_updated_at_reflects_latest_write(repo):
      repo.upsert("concierge", provider="openai")
      first = repo.max_updated_at()
      assert first is not None

      repo.upsert("planner", provider="anthropic")
      second = repo.max_updated_at()
      assert second >= first  # a later write is never an earlier timestamp
  ```

  Run it, expect FAIL: `AttributeError: 'AgentConfigRepository' object has no attribute 'max_updated_at'`.

  Implement in `apps/api/app/repositories/agent_config.py`. Add `from sqlalchemy import func` to
  the existing imports, then add this method to `class AgentConfigRepository` (near `list_all`):

  ```python
      def max_updated_at(self) -> str | None:
          """Return the most recent ``updated_at`` across every row, or ``None`` if empty.

          Cheap cross-process freshness probe (GH-106): a single scalar, not a
          full ``list_all()`` reload. ``updated_at`` is an ISO-8601 string
          (``TimestampMixin``), so ``MAX()`` sorts correctly as text on both
          SQLite and Postgres.

          :return: The lexicographically greatest ``updated_at``, or ``None``.
          """
          with self._session() as s:
              return s.query(func.max(models.AgentConfig.updated_at)).scalar()
  ```

- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_repo.py -x`
- **Done:** Both new tests pass; existing tests in the same file stay green.

### Task 1.2 — Reflection-checkbox CSS fix (wave 1)

- **Files:** `apps/api/app/templates/agent_config.html`, `apps/api/tests/api/agent_config/test_agent_config_dashboard.py`
- **Action:** Root cause (confirmed during brainstorming against the live template and a running
  Docker container — not a stale-build issue): `.am-field { display: flex; ... }` (an author CSS
  rule) overrides the `hidden` HTML attribute's implicit `display: none` on
  `#am-enabled-field` (`<label class="am-field am-check" id="am-enabled-field" hidden>`), so the
  "Reflection enabled" checkbox stays visible for every agent even though the JS already correctly
  sets `enField.hidden = !isRefl` for non-`reflection` agents. `disabled` on the inner inputs
  already works (no data-integrity issue) — this is a visual-only bug.

  Test-first — add to `apps/api/tests/api/agent_config/test_agent_config_dashboard.py`:

  ```python
  def test_reflection_checkbox_has_hidden_override_rule(client):
      # GH-106: `.am-field { display: flex }` overrode the `hidden` attribute on
      # #am-enabled-field, so the checkbox rendered visible on every agent, not
      # just `reflection`. An ID-scoped rule (specificity beats the .am-field
      # class rule without !important) fixes it.
      r = client.get("/dashboard/agent-config")
      assert r.status_code == 200
      assert "#am-enabled-field[hidden]" in r.text
      assert "display: none" in r.text
  ```

  Run it, expect FAIL (rule not present yet).

  Implement: in `apps/api/app/templates/agent_config.html`, in the `<style>` block, immediately
  after the existing `.am-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }`
  rule, add:

  ```css
    #am-enabled-field[hidden] { display: none; }
  ```

  Do not touch `agent_config_edit.html` — it already gates the checkbox block server-side
  (`{% if agent_name == 'reflection' %}`), so it has no `hidden`-attribute-vs-CSS conflict to fix
  (confirmed during spec review).

- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x`
- **Done:** New test passes; all existing `test_agent_config_dashboard.py` tests stay green
  (this task changes no markup structure, only adds one CSS rule).

---

## Chunk 2: Version-poll cache logic

### Task 2.1 — Rename + lower the poll-interval setting (wave 2)

- **Files:** `apps/api/app/core/config.py`, `apps/api/app/core/lifespan.py`
- **Action:** The setting currently named `agent_config_cache_ttl_seconds` (default `3600`)
  described "how long before an unconditional full reload." Its new meaning is "how long before
  the next cheap poll" — rename it so the name doesn't mislead a future reader, and lower the
  default to `5`. Exactly 2 references in the repo (confirmed via grep): the setting definition
  and the one call site in `lifespan.py`.

  In `apps/api/app/core/config.py`, replace:

  ```python
      # How long the DB-backed per-agent config cache may serve before a read
      # reloads it from the DB (MIN-47). Default ~1h: config edits take effect
      # within this window without a restart; normal reads stay in-memory.
      agent_config_cache_ttl_seconds: int = 3600
  ```

  with:

  ```python
      # How long the DB-backed per-agent config cache may serve before a read
      # polls the DB for a change (GH-106: a cheap MAX(updated_at) check, not a
      # full reload — the full reload only happens if that value changed).
      # Default a few seconds: cross-process config edits become visible without
      # a restart and without an expensive reload on every poll.
      agent_config_poll_interval_seconds: int = 5
  ```

  In `apps/api/app/core/lifespan.py`, replace the one call site:

  ```python
      AgentConfigCache.configure(_config_factory, settings.agent_config_cache_ttl_seconds)
  ```

  with:

  ```python
      AgentConfigCache.configure(_config_factory, settings.agent_config_poll_interval_seconds)
  ```

- **Verify:** `cd apps/api && ../../.venv/bin/python -c "from app.core.config import get_settings; assert get_settings().agent_config_poll_interval_seconds == 5; print('ok')"`
- **Done:** Setting renamed everywhere it's referenced (2 call sites); default is `5`; no
  remaining reference to `agent_config_cache_ttl_seconds` in the repo
  (`grep -r agent_config_cache_ttl_seconds apps/api` returns nothing).

### Task 2.2 — `AgentConfigCache` version-poll + fail-open error handling (wave 3)

- **Files:** `apps/api/app/core/agent_config_cache.py`, `apps/api/tests/core/test_agent_config_cache.py`
- **Action:** Replace the unconditional "past TTL → always full reload" logic with "past the poll
  interval → do a cheap `max_updated_at()` check; only run the expensive `reload_from_db()` if
  that value actually changed." Any DB error during either step must not propagate into the
  request path — log it and keep serving the last-known-good cache (retry next interval). This
  depends on Task 1.1 (`max_updated_at()`) and Task 2.1 (renamed setting) both being in place.

  **Step 1 — rewrite the two tests that assert the OLD unconditional-reload behavior.** These
  currently pass a bare string `"FACTORY"` as the session factory and monkeypatch only
  `reload_from_db`; under the new design `_maybe_refresh()` calls `max_updated_at()` *before*
  deciding whether to reload, so both must also mock that call. In
  `apps/api/tests/core/test_agent_config_cache.py`, replace:

  ```python
  def test_get_reloads_from_db_when_stale(monkeypatch):
      calls = []
      monkeypatch.setattr(
          "app.core.agent_config_cache.reload_from_db",
          lambda factory: calls.append(factory),
      )
      AgentConfigCache.configure("FACTORY", ttl_seconds=3600)
      AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past TTL

      AgentConfigCache.get("concierge")

      assert calls == ["FACTORY"]  # a single reload was triggered


  def test_get_skips_reload_when_fresh(monkeypatch):
      calls = []
      monkeypatch.setattr(
          "app.core.agent_config_cache.reload_from_db",
          lambda factory: calls.append(factory),
      )
      AgentConfigCache.configure("FACTORY", ttl_seconds=3600)
      AgentConfigCache._loaded_at = time.monotonic()  # fresh

      AgentConfigCache.get("concierge")

      assert calls == []  # within TTL → no DB hit
  ```

  with:

  ```python
  def test_get_reloads_when_poll_detects_a_change(monkeypatch):
      reload_calls = []
      monkeypatch.setattr(
          "app.core.agent_config_cache.max_updated_at",
          lambda factory: "2026-07-21T00:00:01+00:00",
      )
      monkeypatch.setattr(
          "app.core.agent_config_cache.reload_from_db",
          lambda factory: reload_calls.append(factory),
      )
      AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
      AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"  # stale
      AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

      AgentConfigCache.get("concierge")

      assert reload_calls == ["FACTORY"]  # poll saw a change -> full reload
      assert AgentConfigCache._known_updated_at == "2026-07-21T00:00:01+00:00"


  def test_get_skips_reload_when_poll_sees_no_change(monkeypatch):
      reload_calls = []
      monkeypatch.setattr(
          "app.core.agent_config_cache.max_updated_at",
          lambda factory: "2026-07-21T00:00:00+00:00",
      )
      monkeypatch.setattr(
          "app.core.agent_config_cache.reload_from_db",
          lambda factory: reload_calls.append(factory),
      )
      AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
      AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"  # matches
      AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

      AgentConfigCache.get("concierge")

      assert reload_calls == []  # poll ran, nothing changed -> no expensive reload


  def test_get_skips_poll_when_interval_not_elapsed(monkeypatch):
      poll_calls = []
      monkeypatch.setattr(
          "app.core.agent_config_cache.max_updated_at",
          lambda factory: poll_calls.append(factory) or "x",
      )
      AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
      AgentConfigCache._loaded_at = time.monotonic()  # fresh

      AgentConfigCache.get("concierge")

      assert poll_calls == []  # within interval -> no DB hit at all
  ```

  Run these, expect FAIL (old attribute names / behavior not implemented yet).

  **Step 2 — add error-handling + cross-process tests.** Append to the same file:

  ```python
  def test_poll_failure_keeps_serving_stale_cache(monkeypatch):
      def _boom(factory):
          raise RuntimeError("db unreachable")

      monkeypatch.setattr("app.core.agent_config_cache.max_updated_at", _boom)
      AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
      AgentConfigCache.sync_from_cache({"concierge": AgentModelOverride(provider="openai")})
      AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

      result = AgentConfigCache.get("concierge")  # must not raise

      assert result == AgentModelOverride(provider="openai")  # stale value still served


  def test_reload_failure_keeps_serving_stale_cache(monkeypatch):
      monkeypatch.setattr(
          "app.core.agent_config_cache.max_updated_at",
          lambda factory: "2026-07-21T00:00:01+00:00",  # different -> would reload
      )

      def _boom(factory):
          raise RuntimeError("db unreachable")

      monkeypatch.setattr("app.core.agent_config_cache.reload_from_db", _boom)
      AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
      AgentConfigCache.sync_from_cache({"concierge": AgentModelOverride(provider="openai")})
      AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"
      AgentConfigCache._loaded_at = time.monotonic() - 10_000

      result = AgentConfigCache.get("concierge")  # must not raise

      assert result == AgentModelOverride(provider="openai")  # stale value still served


  def test_cache_detects_a_write_made_without_invalidate(tmp_path):
      # GH-106: models "another process" writing via the repository directly —
      # AgentConfigCache.invalidate() (this process's own same-process signal)
      # is deliberately never called. The fix is that THIS cache still picks up
      # the change through the poll once the interval elapses.
      url = f"sqlite:///{tmp_path / 'cross_process.db'}"
      factory = get_session_factory(url)
      Base.metadata.create_all(get_engine(url), checkfirst=True)
      repo = AgentConfigRepository(factory)
      repo.upsert("reflection", enabled=True)

      AgentConfigCache.configure(factory, poll_interval_seconds=3600)
      reload_from_db(factory)
      assert AgentConfigCache.get("reflection").enabled is True

      repo.upsert("reflection", enabled=False)  # the "other process"'s write
      AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

      assert AgentConfigCache.get("reflection").enabled is False  # picked up via poll
  ```

  Run all new/changed tests, expect FAIL (implementation below not yet written).

  **Step 3 — implement.** In `apps/api/app/core/agent_config_cache.py`:

  Add `import logging` to the top-of-file imports and a module logger right after the existing
  imports:

  ```python
  logger = logging.getLogger(__name__)
  ```

  Rename the fallback constant and update the module docstring's stale "~1h" description:

  ```python
  # Fallback poll interval (seconds) until ``configure`` wires the settings-driven value.
  _DEFAULT_POLL_INTERVAL_SECONDS = 5.0
  ```

  In `class AgentConfigCache`, rename `_ttl_seconds` → `_poll_interval_seconds`, add
  `_known_updated_at`, and rewrite `configure`/`_maybe_refresh`/`clear`:

  ```python
      _cache: dict[str, AgentModelOverride] = {}
      _generation: int = 0
      _loaded_at: float | None = None
      _known_updated_at: str | None = None
      _poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS
      _session_factory = None

      @classmethod
      def configure(cls, session_factory, poll_interval_seconds: float) -> None:
          """Wire the DB loader + poll interval used for lazy refresh (called at startup).

          :param session_factory: Callable returning a session (context manager).
          :param poll_interval_seconds: Max cache age before the next read polls the DB.
          """
          cls._session_factory = session_factory
          cls._poll_interval_seconds = poll_interval_seconds
  ```

  ```python
      @classmethod
      def _maybe_refresh(cls) -> None:
          """Poll the DB for a change past the interval; reload only if something changed.

          Fails open on any DB error: keeps serving the last-known-good cache and
          retries on the next interval, rather than raising into the request path
          (GH-106 — polling runs far more often than the old 1h TTL, so a
          transient DB hiccup must not break every in-flight request).
          """
          if cls._session_factory is None:
              return  # no loader wired (tests drive the cache via sync_from_cache)
          if (
              cls._loaded_at is not None
              and time.monotonic() - cls._loaded_at < cls._poll_interval_seconds
          ):
              return
          # Stamp first so a slow poll doesn't let concurrent readers stampede.
          cls._loaded_at = time.monotonic()
          try:
              latest = max_updated_at(cls._session_factory)
          except Exception as exc:  # noqa: BLE001 - fail open on any DB error
              logger.error(f"[AgentConfigCache] poll failed, serving stale cache: {exc}")
              return
          if latest == cls._known_updated_at:
              return
          try:
              reload_from_db(cls._session_factory)
          except Exception as exc:  # noqa: BLE001 - fail open on any DB error
              logger.error(f"[AgentConfigCache] reload failed, serving stale cache: {exc}")
              return
          cls._known_updated_at = latest

      @classmethod
      def clear(cls) -> None:
          """Reset the cache and all refresh state (tests)."""
          cls._cache = {}
          cls._generation = 0
          cls._loaded_at = None
          cls._known_updated_at = None
          cls._session_factory = None
          cls._poll_interval_seconds = _DEFAULT_POLL_INTERVAL_SECONDS
  ```

  `invalidate()` is unchanged (still just resets `_loaded_at`, forcing this process's next read to
  poll immediately — same-process instant refresh, unrelated to `_known_updated_at`).

  Add the module-level poll helper next to `reload_from_db` (same file, mirrors its shape and its
  local-import style to avoid a module-level `core` → `repositories` import):

  ```python
  def max_updated_at(session_factory) -> str | None:
      """Return the most recent ``updated_at`` across every ``agent_config`` row.

      Cheap freshness probe used by ``_maybe_refresh`` before paying for a full
      ``reload_from_db``. ``None`` when the table is empty.

      :param session_factory: Callable returning a new session (context manager).
      :return: The lexicographically greatest ISO-8601 ``updated_at``, or ``None``.
      """
      from app.repositories.agent_config import AgentConfigRepository

      return AgentConfigRepository(session_factory).max_updated_at()
  ```

  No new imports needed in `apps/api/tests/core/test_agent_config_cache.py` — `Base`,
  `get_engine`, `get_session_factory`, and `AgentConfigRepository` are already imported at the top
  of that file (used by the pre-existing `test_reload_from_db_reflects_an_upsert`).

- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x`
- **Done:** All tests in the file pass — the 2 rewritten tests, the 3 new poll/error-handling
  tests, the 1 new cross-process test, and every pre-existing test
  (`test_sync_from_cache_replaces_map`, `test_get_returns_none_for_unknown_agent`,
  `test_override_carries_enabled_flag`, `test_clear_empties_cache`,
  `test_reload_from_db_reflects_an_upsert`, `test_generation_bumps_only_when_data_changes`,
  `test_no_reload_without_configure`, `test_invalidate_forces_next_read_to_reload`) untouched and
  green.

---

## Chunk 3: Full verify

### Task 3.1 — Lint + full targeted suite (wave 4)

- **Files:** `apps/api/app/repositories/agent_config.py`, `apps/api/app/core/agent_config_cache.py`, `apps/api/app/core/config.py`, `apps/api/app/core/lifespan.py`, `apps/api/app/templates/agent_config.html`
- **Action:** Run `ruff` on every changed Python file and the full set of tests this change
  touches (cache, repo, dashboard, plus the two existing files the design flagged as
  behavior-unchanged: `tests/agents/test_agent_context.py`, `tests/agents/test_depth_toggles.py`)
  to confirm no regressions across the slice. Fix any lint/format findings on newly-written code
  (Rule 3).
- **Verify:** `cd apps/api && ruff check app && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py tests/api/agent_config tests/agents/test_agent_context.py tests/agents/test_depth_toggles.py -x -q`
- **Done:** `ruff` clean on `app/`; every test in the targeted set passes.

---

## Waves

| Wave | Tasks | Parallel? | Files disjoint |
|---|---|---|---|
| 1 | 1.1 `max_updated_at()`, 1.2 CSS fix | 2 parallel | `repositories/agent_config.py`+its test · `templates/agent_config.html`+dashboard test |
| 2 | 2.1 settings rename | single | `core/config.py`, `core/lifespan.py` |
| 3 | 2.2 cache poll logic | single | `core/agent_config_cache.py`+its test (depends on 1.1 + 2.1) |
| 4 | 3.1 full verify | single | (verify only) |

## Risks

- **Rule-4 hard gate: "replacing a service/pattern"** — acknowledged at intake/escalation
  (E001) and in `design.md` §8; mitigated by zero new infra/dependency and a strictly tighter
  propagation bound for the only deployment topology that exists today.
- **CSS `<verify>` is a static text assertion, not a real browser render** (see Plan-time
  decisions) — confirms the fix is *present*, not that the cascade *renders* correctly in every
  browser. Low residual risk: the rule is a textbook ID-beats-class specificity case with no
  known browser exception; a manual screenshot re-check post-merge is good practice but not gated.
- **Settings rename** — exactly 2 call sites (confirmed via grep), no `.env.example`/docs
  reference the old name; low blast radius, but note in the PR description in case any
  out-of-repo deploy config sets `AGENT_CONFIG_CACHE_TTL_SECONDS`.
- **Redundant reload on first poll after process start** — `lifespan.py`'s startup-time direct
  `reload_from_db()` call doesn't set `_known_updated_at` (only the poll path in `_maybe_refresh`
  does), so the first poll after startup always sees an apparent "change" and reloads once more
  than strictly necessary. Harmless at this table's size; not worth special-casing.

## Rollback

- Revert code: `git revert <sha>` for each task commit — no migration to undo, every change is
  additive/renamed code plus one CSS rule.

## Status log

- 2026-07-21 — plan drafted from approved `design.md` + `research-brief.md`; 5 tasks / 4 waves.
- 2026-07-21 — executed (subagent-driven, in-session). Wave 1 (parallel): Task 1.1 `835d26b`
  (+docstring fix `804995d` per code-quality review), Task 1.2 `72a0ff9` (+test-strength fix
  `e18c790` per code-quality review). Wave 2: Task 2.1 `70c4dc5` (+stale-comment fix `a95d816`
  per spec review). Wave 3: Task 2.2 `b0da5ab` (+concurrency-race fix `ec0550f` per code-quality
  review — sync `GraphDep` runs via FastAPI `run_in_threadpool`, so `_maybe_refresh()` needed a
  lock around its poll→reload→known-update sequence; independently re-verified after the fix).
  Wave 4: Task 3.1 verify — clean on first run, no changes needed. All per-task spec + quality
  reviews passed (with fix-and-re-review loops noted above). 72 targeted tests green,
  `ruff check app` clean.
