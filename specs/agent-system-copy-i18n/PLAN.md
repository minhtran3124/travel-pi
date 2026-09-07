# agent-system-copy-i18n — Plan

## 1. Goal

Code-authored agent replies (tier-gate upgrade notice, unknown intent, HITL cancel/approve, error fallback) are emitted in the conversation language. English stays the single source; other languages are translated once by the existing `ContentTranslationService` and cached in `content_translations`; any translation failure serves English.

## Global Constraints

- English constants in `app/agents/constants.py` remain the only source text; no per-language tables.
- `DEFAULT_LANGUAGE` path is a strict no-op (no DB, no LLM).
- `system_reply` never raises; any failure returns the English source.
- No new agent-config node name (translator reuses `TRANSLATOR_AGENT`).
- No schema change: rows use `entity_type="system_copy"`, `entity_id=<key>`, `field="text"`.

## 2. Tasks

### Task 1.1 — Localized system copy helper

- **Files:** apps/api/app/agents/copy.py, apps/api/tests/agents/test_system_copy.py
- **Action:** Add `SYSTEM_COPY: dict[str, str]` (key → English constant) and `system_reply(key, language, *, translator=None) -> str`: default language returns the source untouched; otherwise open `session_scope()` and call `ContentTranslationService(s, translator).localize("system_copy", [_Copy(id=key, text=source)], ["text"], language)`; wrap in try/except returning the source on any error. Tests: en no-op with no DB access; vi translated via fake translator and cached (second call zero translator calls); translator raising → English; every key non-empty.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q`
- **Done:** helper passes tests; keys: booking_upgrade, unknown_intent, booking_cancelled, plan_approved, agent_error_fallback.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes the existing content-translation service and the tool DB-scope helper (pre-existing code); produces `app/agents/copy.py` exporting `system_reply`.

### Task 1.2 — Route the five call sites through system_reply

- **Files:** apps/api/app/agents/supervisor.py, apps/api/app/agents/nodes.py, apps/api/app/routers/agent.py, apps/api/app/streaming/mapper.py, apps/api/tests/agents/test_system_copy.py
- **Action:** supervisor: compute `lang` (intent.language or state language) BEFORE the unknown-intent and tier-gate branches and emit `system_reply("unknown_intent"/"booking_upgrade", lang)`. nodes plan node: `system_reply("booking_cancelled"/"plan_approved", state.get("language"))`. router: failure branch reads language from `graph.aget_state(cfg)` best-effort, success-fallback uses `result.get("language")`. mapper: use tracked `current_language`. Add a grep test asserting no literal `AIMessage(content="` remains under app/agents, app/routers/agent.py, app/streaming.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents tests/api/agent -q`
- **Done:** all five sites go through `system_reply`; existing suites green.
- **Criteria:** SC-4, SC-5
- **Interfaces:** Consumes `system_reply` from `app/agents/copy.py`; produces `app/agents/supervisor.py`, `app/agents/nodes.py`, `app/routers/agent.py`, `app/streaming/mapper.py`.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | English is a no-op, no DB/LLM | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k default` | exit 0 |
| SC-2 | vi translated once and cached | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k cache` | exit 0 |
| SC-3 | Translator failure serves English | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k fail` | exit 0 |
| SC-4 | Tier-gate reply uses the turn's detected language | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k supervisor` | exit 0 |
| SC-5 | No literal user-facing AIMessage outside copy helper | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py -q -k no_literal` | exit 0 |
