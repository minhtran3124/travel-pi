---
ticket: 348
stage: plan
status: needs-review
needs_review: true
confidence: medium
decided_by: claude (ship workflow: plan)
date: 2026-10-31
---

# 0008. thread_id format changes only for new non-default-bot conversations

## Context

Adding bot to thread_id for old threads would orphan existing checkpoints.

## Options

- change format for all threads
- change only for conversations created after migration, omit segment for default bot

## Decision

Change only for new non-default-bot conversations; old threads keep their id.

## Why

Avoids stored-data breakage; conversation_id is already unique.

## Consequences

_thread_id needs the conversation's stored bot.

## How to reverse

Drop the segment from _thread_id; no data rewrite needed.
