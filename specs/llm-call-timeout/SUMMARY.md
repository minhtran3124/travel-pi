# llm-call-timeout — Summary

Lane: normal
Confidence: medium
Reason: no hard gate; 1 flag (existing behavior — long calls now raise and enter LLM_RETRY) but 2 files (config.py setting + llm.py), so not tiny
Flags: existing-behavior
Affects: app/clients/llm.py (_build_chat_model — every LLM call), app/core/config.py
Input-type: spec slice
Route: using-git-worktrees → subagent-driven-development
Escalate: no

> Documented default (why medium): a single `llm_timeout_seconds` setting, default **120s**, passed as `timeout=` through `init_chat_model`. All three SDKs in use accept that kwarg: langchain-openai 1.6.2 `request_timeout` (alias `timeout`), langchain-anthropic 1.7.2 `default_request_timeout` (alias `timeout`), and langchain-google-genai 4.4.0 `timeout`.
> Correction to research-brief §2: calls are NOT unbounded today. The openai and anthropic SDKs default to `httpx.Timeout(600, connect=5)`. So this slice *lowers the timeout and makes it configurable*, rather than adding one.
> Evidence for 120s, from the dev DB (`agent_run_steps` where kind=llm, n=777): gpt-5.4-mini has p99 4.8s and max 6.8s; gpt-5 has p99 27.6s and max 31.3s. 120s is about 4x the slowest call observed. Timeouts are already retried by `LLM_RETRY` (`app/agents/retry.py:45-55`).

### Intent

> make research for
> - https://www.langchain.com/blog/langsmith-llm-gateway-runtime-controls-for-production-agents
> - https://www.langchain.com/langsmith/llm-gateway
> - https://www.langchain.com/blog/how-we-made-coding-agent-spend-predictable
>
> làm 1 nghiên cứu đnahs gía để áp dụng vào project hiện tại

> ok, run /feature-intake cho nhung de xuat o trren

> /feature-intake "and  start for llm-call-timeout"

Source backlog: `specs/llm-gateway-eval/research-brief.md` §4 (7 items). This slice covers: item 3 (LLM request timeout).

## What changed

Intake only — not implemented.

### Rationale

Every chat model is built in one place (_build_chat_model), so one kwarg covers all nodes; the retry layer already treats timeouts as transient.

### Alternatives considered

- Per-node timeout in agent_config — deferred: needs a schema change; add only if one global value proves wrong.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |

### Not auto-verified

- Lane/Confidence classification — reached traceability; judged from `research-brief.md` §2 evidence, no diff exists yet.

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
