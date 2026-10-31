---
ticket: 348
stage: plan
status: needs-review
needs_review: true
confidence: medium
decided_by: claude (ship workflow: plan)
date: 2026-10-31
---

# 0007. Config key becomes (bot_id, agent_name) with fall-through to global agent_config

## Context

AgentConfigCache is keyed by agent_name only.

## Options

- (bot_id, agent_name) with fallback to global row
- per-bot overrides only in bots.model_overrides, cache unchanged

## Decision

Cache key (bot_id, agent_name); resolution order bot override, global agent_config row, env default; bot_id=None means default bot.

## Why

Keeps current callers working and matches the ticket; the cache interface changes.

## Consequences

Touches llm.py, graph.py, router; needs regression tests.

## How to reverse

Revert the key change; bot overrides fall back to global rows.
