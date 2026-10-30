---
ticket: 344
stage: uat
status: needs-review
needs_review: true
confidence: high
decided_by: claude (ship workflow: uat)
date: 2026-10-30
---

# 0003. UAT not run for #344

## Context

The UAT stage could not check the running app: The app started from the uat-344 worktree, using the t344 venv because the worktree has none. GET /dashboard/bots returned 401 "DashboardLoginRequired". VERIFY_USER and VERIFY_PASSWORD are unset. The config has no env map to wire them into the app. No "throwaway credentials OK" consent exists in the request, so I did not invent credentials. No browser scenarios were run and no code was changed.

## Options

- n/a

## Decision

Continue without UAT; the ticket stays done and the PR body says UAT did not run.

## Why

A missing config, a start failure or an agent failure is not an acceptance failure, so no code fix is attempted.

## Consequences

The running app was not checked against the original request.

## How to reverse

Run /harness:uat 344 by hand.
