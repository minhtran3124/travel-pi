---
ticket: 348
stage: intent
status: needs-review
needs_review: true
confidence: medium
decided_by: claude (ship workflow: intent)
date: 2026-10-31
---

# 0005. Profile storage: bots table, not config files

## Context

Ticket proposes a table `bots`; the alternative is versioned files in the repo.

## Options

- bots DB table
- versioned YAML/JSON files only

## Decision

Recommend a `bots` table seeded from versioned files for prompts.

## Why

Matches the ticket's candidate and the existing agent_config DB pattern; prompts stay in versioned files.

## Consequences

Requires an Alembic migration (high-risk lane).

## How to reverse

Drop the table and revert the config key change; plan only, so nothing to undo now.
