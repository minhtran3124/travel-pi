---
ticket: 344
stage: plan
status: accepted
needs_review: false
confidence: high
decided_by: claude (ship workflow: implement)
date: 2026-10-30
---

# 0002. The dashboard calls containers "instances"

## Context

The Bots page called a container a "bot". That clashes with chatbot personas, where "bot" means the assistant a user talks to.

## Options

- Change wording only: visible strings, nav label, docstrings and docs.
- Also rename the route, the table `bot_heartbeats`, the env vars and the classes. This needs a migration and breaks deploys, with no user-visible gain.

## Decision

Change wording only. English says "Instance(s)". Vietnamese uses the loanword "instance" (not "phiên bản", which means "version").

## Why

It is the smallest diff that frees the word "bot" for personas.

## Consequences

Kept unchanged:

- URL `/dashboard/bots` and `bots.json`
- table `bot_heartbeats`
- env var `BOT_INSTANCE_ID`
- env var `BOT_ROLE`
- class, file, CSS class and element id names (for example `bots-empty`)

Code still says "bot" internally. `render.yaml` does not set `BOT_INSTANCE_ID`, so on Render the identity falls back to `RENDER_INSTANCE_ID` (then hostname) and no deploy change is needed. Pinning a friendly id such as `api-1` is a separate follow-up (see ADR 0004). The mascots stay infrastructure characters, separate from Tin's mark (the lime "T" in `apps/web/src/components/chat/AgentAvatar.tsx`).

## How to reverse

Restore the old strings in `bots.html`, the nav label in `base.html` and the docstrings.
