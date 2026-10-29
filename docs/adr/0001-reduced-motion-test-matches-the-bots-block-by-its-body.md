---
ticket: 329
stage: implement
status: accepted
needs_review: false
confidence: medium
decided_by: claude (ship workflow: implement)
date: 2026-10-29
---

# 0001. Reduced-motion test matches the bots block by its body

## Context

The base layout also contains the string prefers-reduced-motion (6 occurrences in rendered page)

## Options

- count whole string
- match the bots block text

## Decision

Assert exactly one bots-template block with the animation:none rule

## Why

Whole-page count is not controlled by this template

## Consequences

Test depends on that block's exact text

## How to reverse

Edit the test
