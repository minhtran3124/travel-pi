# agent-system-copy-i18n — Summary

Lane: normal
Confidence: high
Reason: no manifest hard gate; flags = existing behavior (reply text of 5 code-authored agent messages changes per language) + multi-file (constants, supervisor, nodes, router, mapper, new copy module, tests) → normal.
Flags: existing-behavior
Affects: app/agents (supervisor tier gate, HITL plan node), app/routers/agent.py + app/streaming/mapper.py (error fallback); no route/envelope change
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> check screenshot, we should translate the message "Booking is a premium ..." matching with current user's language
> /feature-intake review current codebase and find the best solution to hande this case and similar case in the future

(Screenshot: Vietnamese conversation; user says "ok, book cho mình cái rẻ nhất đi"; bot replies in English "Booking is a premium feature. Please upgrade your plan to book trips.")

## What changed

Added `app/agents/copy.py` (`SYSTEM_COPY` + `system_reply(key, language)`): English constants stay the source; non-default languages are translated once via `ContentTranslationService` (`entity_type="system_copy"`) and cached in `content_translations`; any failure serves English. The five code-authored reply sites (supervisor unknown-intent + tier gate, HITL plan cancel/approve, REST + SSE error fallback) now go through it; the supervisor resolves this turn's detected language before its terminal branches. A grep test forbids new literal `AIMessage(content="...")` outside the helper.

### Findings (codebase review)

All agent replies produced by the LLM already follow `state["language"]` (centralized via `with_reply_language`, see memory `agent-reply-language-centralized-default-en`). The leak is the set of replies authored **in Python code**, which bypass the LLM and are emitted as plain English `AIMessage`s regardless of language:

| # | Message | Where | Language available at emission? |
| --- | --- | --- | --- |
| 1 | `BOOKING_UPGRADE_MSG` "Booking is a premium feature…" | `app/agents/supervisor.py:280` tier gate | yes — `intent.language` from `router.invoke` is already computed a few lines above; fallback `state["language"]` |
| 2 | "I'm not sure how to help with that yet." | `app/agents/supervisor.py:269` unknown intent | yes (same) |
| 3 | "Booking cancelled as requested." | `app/agents/nodes.py:280` HITL plan node | yes — `state["language"]` |
| 4 | "Plan approved. Proceeding with booking." | `app/agents/nodes.py:286` | yes |
| 5 | `AGENT_ERROR_FALLBACK_MSG` | `app/routers/agent.py:404,460`, `app/streaming/mapper.py:346` | partial — mapper already reads `pre_lang` from the pre-run checkpoint; router can read the same checkpoint; default `en` |

Existing precedents that constrain the design:
- `app/core/languages.py` is the SoT: only `en`/`vi`, `normalize()`, `DEFAULT_LANGUAGE="en"`.
- `app/streaming/panel_localizer.py`: deterministic BE-side `vi` lookup tables, `en` identity no-op (docs/solutions `side-panel-language-decisions`: deterministic-over-LLM).
- Suggestion chips use the opposite pattern (BE returns keys, FE resolves via `Chat.followups`). That pattern does **not** fit here: these strings are persisted as assistant message `content` via `repo.append_message` and replayed from history, so the stored text itself must already be localized.

### Rationale

Revised after user pushback ("bảng tĩnh không scale khi nhiều ngôn ngữ"). Recommended: **English source + translate-once-and-cache**, reusing `ContentTranslationService` (specs/catalog-content-i18n). System copy stays as English constants in `app/agents/constants.py` (the single source, `DEFAULT_LANGUAGE` is a strict no-op); a thin `system_reply(key, language)` in `app/agents/copy.py` opens `session_scope()` and calls `localize("system_copy", [Copy(id=key, text=EN)], ["text"], language)`. First hit per `(key, language)` costs one LLM translator call and is written back to `content_translations`; every later hit is a DB read, deterministic. Translator failure or LLM outage keeps English (the service never raises), which also covers `AGENT_ERROR_FALLBACK_MSG`. Adding a language = adding a code to `SUPPORTED_LANGUAGES`; adding a message = adding one English constant. Zero manual translation. The supervisor tier gate uses the freshly detected `intent.language`.

Convention for the future: no user-facing literal `AIMessage(content="...")` outside `constants.py` + `system_reply`; enforce with a grep test over `app/agents`, `app/routers/agent.py`, `app/streaming`.

### Alternatives considered

- **Static `{en, vi}` table per message** (first proposal) — rejected by user: N messages × M languages of hand translation; does not scale.
- **Instruction-to-the-model** (the `NO_ACTIVE_TRIP_MSG` pattern: inject a SystemMessage and let the reply LLM phrase it) — viable for #1–#4 but costs an extra LLM call every time, wording drifts, and #5 fires when the LLM is down. Keep as fallback option if cached translations read badly.
- **BE returns a key, FE resolves via next-intl** (suggestions pattern) — rejected: assistant messages are persisted and replayed as `content`; MCP/REST clients would show raw keys; FE catalog would still need M languages by hand.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| helper unit tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q` | 0 | 9 passed | |
| SC-1 en no-op | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k default` | 0 | | SC-1 |
| SC-2 cache | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k cache` | 0 | | SC-2 |
| SC-3 failure→en | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k fail` | 0 | | SC-3 |
| SC-4 supervisor lang | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k supervisor` | 0 | | SC-4 |
| SC-5 no literal | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k no_literal` | 0 | | SC-5 |
| agent suites | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/agents tests/api/agent -q` | 0 | 504 passed (without the override, `.env` points at a stopped Postgres and TestClient-lifespan tests error at setup — pre-existing) | |
| full BE suite (SQLite) | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest -q` | 1 | 59 failed / 2120 passed; the identical 59 (dashboard/prompts/info/config, env-related) fail on `main` with the same command — pre-existing, not introduced | |
| lint | `cd apps/api && ruff check app tests/agents/test_system_copy.py` | 0 | (`scripts/seed_supabase_user.py` I001 is pre-existing on main) | |

### Not auto-verified

- Real Vietnamese wording + live behaviour — reached **truth** via UAT on the dev stack (2026-09-07, `screenshots/uat-agent-system-copy-i18n/README.md`): free-user tier gate (the reported screenshot case), HITL cancel, HITL approve all served in Vietnamese; `unknown_intent` / `agent_error_fallback` not reachable from the UI (unit-tested; LLM-translated in the container).
- Independent review (general-purpose reviewer, read-only): Spec PASS / Quality PASS; major finding (sync translation on the event loop in async REST/SSE fallbacks) fixed with `asyncio.to_thread`; minor findings (stale cache on source edit → row id now carries a source digest; grep guard widened to `'`/f-strings/`*_MSG` constants; plan-node `vi` test added) fixed in the follow-up commit.

### Rollback

- `git revert <sha>` (not applicable at intake)

### Harness-Delta

- none

## Route

- Escalate: no
- Route: `using-git-worktrees` → `writing-plans` (>3 steps, >2 files) → `subagent-driven-development`; branch `feat/agent-system-copy-i18n` off `main`.
