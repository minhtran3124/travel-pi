# Assumption: Drive the agent in-process

## Context
Live API at :8000 requires a Supabase JWT. The signing material lives only in the denied apps/api/.env, so no Bearer token could be minted.

## Decision
Ran a scratchpad script (bk.py) with FastAPI TestClient and the get_current_user dependency overridden. It used the same Postgres DB, the real Anthropic API and the worktree sources, with LLM_PROVIDER=anthropic, LLM_MODEL=claude-sonnet-5-5, FAST_LLM_MODEL=claude-haiku-5-5 as process env. The 401 path was checked on the live port with curl.

## Alternatives
- Forge a JWT (needs secrets, not allowed).
- Edit code to add an auth bypass (testers must not edit code).

## Impact if wrong
The live uvicorn process did not serve these agent calls. Code, DB, agent_config rows and provider are identical, so routing and model attribution are still valid evidence. Auth middleware itself is only covered by the 401 curl check.

## How to reverse
Nothing to undo. The script lives in the scratchpad only. To re-verify through the live port, mint a real token with a test account and replay the same flow.
