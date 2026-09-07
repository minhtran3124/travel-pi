# UAT — chatbot on `/trips` (PII guardrail)

**Date:** 2026-08-28 · **URL:** http://localhost:3000/trips
**Build under test:** `feat/pii-middleware-guardrail` @ `9ed1509` (PR #123)
**Stack:** Next dev on `:3000` (FE identical on both branches — the branch touches only `apps/api`
and `specs/`), API container bind-mounted to the branch worktree, Postgres `api-db-1`.
**Auth:** real Supabase session, captured interactively and reused (`/trips` is gated by
`apps/web/src/lib/supabase/middleware.ts`).

## Result: 9 / 9 PASS

| # | Test case | Result | Evidence |
|---|---|---|---|
| TC01 | `/trips` renders for a signed-in user, no login redirect | PASS | `TC01-trips-authenticated.png` |
| TC02 | Chat launcher opens the assistant panel | PASS | `TC02-chat-panel-open.png` |
| TC03 | Assistant answers an ordinary question, reply complete | PASS | `TC03-plain-question-answered.png` |
| TC04 | Email never persisted; stored + reloaded as `[REDACTED_EMAIL]` | PASS | `TC04a-*.png`, `TC04b-*.png` |
| TC05 | Card never persisted; stored + reloaded as `****-****-****-1111` | PASS | `TC05a-*.png`, `TC05b-*.png` |
| TC06 | Email + card in one turn: neither persisted, both redacted | PASS | `TC06a-*.png`, `TC06b-*.png` |
| TC07 | Non-Luhn digit run NOT masked (no over-redaction) | PASS | `TC07-non-card-digits-untouched.png` |
| TC08 | No raw PII anywhere in the reloaded transcript | PASS | `TC08-full-transcript-clean.png` |
| TC09 | Pre-reload UI echo is browser-local only | PASS (documented) | `TC04a/TC05a/TC06a` |

Machine-readable: `results.json`.

## Database evidence (the real oracle)

The UI can be re-rendered from local state, so redaction was asserted against the DB the API
writes to, not only against pixels:

```sql
-- any email at all in persisted messages
select count(*) from messages
where content ~ '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}';   -- => 0

-- rows carrying redaction markers                                   -- => 7 / 3
select count(*) from messages where content like '%[REDACTED_EMAIL]%';
select count(*) from messages where content like '%****-****-****-1111%';
```

The only bare 13–19 digit runs left in `messages` are the intentional TC07 booking reference
`1234567890123`, which fails Luhn and must not be masked.

## TC09 — pre-reload UI echo (expected, not a leak)

`apps/web/src/components/chat/useAgentStream.ts:295` appends the user bubble optimistically from
the raw typed text, and the raw text is what goes in the request body; redaction is server-side.
So the panel shows the raw value until the next load, while the stored copy is already redacted —
visible by comparing each `*a-*-before-reload.png` with its `*b-*-after-reload.png`.

This matches the shipped contract ("before any LLM call, checkpointer write, or memory
extraction"), which never claimed to scrub the local echo. Worth a product decision only if you
want the bubble to reflect what was actually stored.

## Defect found — PRE-EXISTING on `main`, NOT caused by this PR

Some turns answer with the error fallback *"I ran into a problem handling that request…"*
(visible in `TC05a-card-ui-echo-before-reload.png`). Server-side:

```
File "langgraph/prebuilt/tool_node.py", line 1397, in _inject_tool_args
    raise KeyError(state_field)
KeyError: 'trip_id'
```

A tool declares `trip_id` as injected state, but `_turn_input()` omits the key when the client
sends `trip_id: null` — deliberate, per `specs/fix-trip-id-persist-across-turns`, so a null does
not clobber the checkpointed value. On `/trips` (the list page) there is no active trip, so any
intent routing to a trip-scoped tool raises.

Attribution was verified, not assumed:

1. The PR's diff to `routers/agent.py` only swaps the message argument; it does not touch the
   `if trip_id is not None` conditional or the tool.
2. A **PII-free** message ("Please send my itinerary") reproduces it on the branch.
3. The API container was restored to the `main` checkout (guardrail absent, confirmed) and the
   same PII-free request reproduces the same fallback and the same `KeyError` there.

Not a blocker for PR #123. Worth its own issue.

## Reproducing

Scripts live in the session scratchpad (`login.mjs` captures the Supabase session, `uat2.mjs`
runs the cases). They are not checked in — they hardcode local absolute paths and drive a
headed browser against a live authenticated session.
