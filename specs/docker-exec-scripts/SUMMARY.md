---
slug: docker-exec-scripts
status: shipped
lane: tiny
confidence: high
---

Lane: tiny
Confidence: high
Reason: Zero risk flags — adds Makefile convenience targets only, no app code or contracts touched.
Flags: none
Affects: none
Input-type: Change request
Route: Direct Edit
Escalate: no

### Intent

> create script to exec api and db container

### Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| Makefile parses | `make help` | 0 | new targets appear in help output |
