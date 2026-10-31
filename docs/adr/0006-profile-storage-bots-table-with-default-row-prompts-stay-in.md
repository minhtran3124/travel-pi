---
ticket: 348
stage: plan
status: needs-review
needs_review: true
confidence: medium
decided_by: claude (ship workflow: plan)
date: 2026-10-31
---

# 0006. Profile storage: bots table with default row, prompts stay in versioned files

## Context

Ticket proposes a bots table; alternative is YAML/JSON-only profiles.

## Options

- bots DB table
- versioned YAML/JSON files only

## Decision

Recommend a bots table (implemented as bot_profiles) whose prompt_versions column selects versioned prompt files.

## Why

Matches the ticket candidate and the existing agent_config DB pattern; keeps prompt text reviewable in git.

## Consequences

Requires an Alembic migration (high-risk lane) and a default-bot backfill.

## How to reverse

Drop the table and revert the config key change; nothing exists yet since this is plan only.
