---
problem_type: knowledge
module: agent/reflection
tags: langgraph, checkpointer, poisoned-thread, uvicorn-reload, prompt-versioning
severity: critical
applicable_when: Debugging an AI-agent behavior that appears to repeat across multiple turns of one conversation thread, or verifying a fix/prompt change against a live dev agent.
affects:
  - apps/api/app/prompts/registry.py
  - apps/api/app/agents/checkpointer.py
supersedes: null
confidence: high
confirmed_at: 2026-07-03
---

## Applicable When

Use this pattern whenever debugging an AI-agent behavior that appears to repeat across
multiple turns of one conversation thread, or whenever verifying a fix/prompt change
against a live dev agent — always reset the LangGraph checkpoint tables (not just
message-display tables) for a clean thread, and always force a process restart after
any prompt-only (`.md`/`active.yaml`) edit before re-testing.

## Pattern

LangGraph-checkpointed conversation state (Postgres `checkpoints` /
`checkpoint_writes` / `checkpoint_blobs` / `store`) is a distinct, separate source of
truth from the display-only `messages`/`conversations` tables — and it, not the
display table, is where a "poisoned thread" (a bad tool-error instruction, a
wrong-language turn, etc.) actually persists across future turns. Any tool-error
message or synthetic instruction written into that state repeats on every subsequent
turn in the same thread, verbatim, because the model reads it back as prior context
each time. To cleanly re-test the agent after a code/prompt fix, you must reset the
checkpoint tables, not just the message-history tables — and even then, a prompt-only
(`.md`/`active.yaml`) change won't take effect in a running `uvicorn --reload` dev
container, because that watcher only restarts on `.py` file changes (the prompt
registry is a module-level singleton loaded once at import).

## How to Use

When a bug in the AI agent's behavior appears to repeat/persist across many turns of
the *same* conversation thread (not just once), don't only check the `messages` table
for what was displayed — trace whether the bad content was ALSO written into
`checkpoints`/`checkpoint_writes`/`checkpoint_blobs`/`store` as part of that turn's
`ToolMessage`/`HumanMessage`/`SystemMessage` state update; if so, it will resurface on
every future turn until that thread's checkpoint state is cleared. To get a truly
clean re-test in dev Postgres, truncate all six tables — trimming only
`messages`/`conversations` leaves the poisoned graph state intact and a "fresh" thread
will still misbehave. After any prompt-only edit (`apps/api/app/prompts/**/*.md` or
`active.yaml`, no `.py` touched), the change silently will NOT be picked up by the
running dev `uvicorn --reload` container; force it to reload with
`docker compose restart api` (from `apps/api/`) before verifying, and don't trust a
`docker exec` one-off Python check as a stand-in for the live worker (it re-imports
fresh, so it can show the new prompt content correctly even while the actual serving
process still uses the old one).

## Code Example

```sql
-- Full clean reset for local dev re-testing (not just messages/conversations)
TRUNCATE messages, conversations, checkpoints, checkpoint_writes, checkpoint_blobs, store CASCADE;
```

```bash
# Force uvicorn --reload to pick up prompt/registry .md + .yaml edits
cd apps/api && docker compose restart api
```

## Gotchas

A `docker exec` one-off Python process can show the NEW prompt content (it re-imports
the module fresh) even while the long-running `uvicorn --reload` worker is still
silently serving the OLD version — this makes a naive verification attempt look like
it passed when the running server hasn't actually reloaded. Also: `PromptRegistry`
(`apps/api/app/prompts/registry.py`) is a module-level singleton built once at import
via `reload()`, which scans `*/v*.md` + `active.yaml` — it has no file-watcher of its
own, so it depends entirely on the surrounding process restarting.

## Related

- [local-postgres-checkpointer](local-postgres-checkpointer.md)
- [reflection-humanmessage-language-flip](reflection-humanmessage-language-flip.md)
