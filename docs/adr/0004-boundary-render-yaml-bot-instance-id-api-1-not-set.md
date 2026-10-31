---
ticket: run
stage: intent-fix
status: needs-review
needs_review: true
confidence: high
decided_by: claude (ship workflow: intent-fix)
date: 2026-10-30
---

# 0004. Boundary: render.yaml BOT_INSTANCE_ID=api-1 not set

## Context

Intent review found nothing in the repo sets BOT_INSTANCE_ID=api-1 for the Render lite deploy, while ADR 0002 says Render sets it. The only in-repo place to set it is render.yaml, which is not in the ticket's file list. The ticket also lists the BOT_INSTANCE_ID env var as out of scope.

## Options

- Edit render.yaml to add BOT_INSTANCE_ID=api-1
- Reword the ADR to say the value is set in the Render dashboard (unverified)
- Skip and leave to the owner

## Decision

Skip: change nothing.

## Why

render.yaml is outside the allowed file set and the ticket puts the env var out of scope. Rewording the ADR would assert an unverifiable claim.

## Consequences

The lite deploy may show the Render-assigned or hostname instance id instead of api-1 until the owner adds the env var in render.yaml or the dashboard.

## How to reverse

Add an envVars entry BOT_INSTANCE_ID=api-1 to the api service in render.yaml in a follow-up, or set it in the Render dashboard.
