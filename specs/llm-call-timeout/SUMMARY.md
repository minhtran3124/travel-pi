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
> Correction, made during correctness review: before this change the calls were **unbounded**, not 600s. langchain passes `timeout=None` explicitly (`langchain_openai/chat_models/base.py:1391`, `langchain_anthropic/chat_models.py:1460`), and the SDK's `DEFAULT_TIMEOUT` only applies when the argument is NotGiven. A probe confirmed `ChatOpenAI(model="gpt-5").root_client.timeout` is None. The intake note that said "600s" was wrong.
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

Every chat model now gets a 120s idle timeout by default, set by `LLM_TIMEOUT_SECONDS`. Before this change it had none at all. This is a connect / gap-between-reads bound, not a cap on total duration.
- On the chat graph, a timeout is retried by `LLM_RETRY`.
- The deep-research models (`trip_research`, `trip_research_grader`) run on a graph with no LLM retry, so they instead receive `timeout=research_timeout_s` (600s). This uses a new optional `timeout=` override on `get_agent_llm` / `get_llm`, so one slow call can no longer fail a whole research run.

### Rationale

Every chat model is built in one place (_build_chat_model), so one kwarg covers all nodes; the retry layer already treats timeouts as transient.

### Alternatives considered

- Per-node timeout in agent_config — deferred: needs a schema change; add only if one global value proves wrong.

### Deviations

- Rule 1: three test modules outside the Files set (`tests/clients/test_llm.py`, `test_get_agent_llm_db_config.py`, `test_llm_stream_usage.py`) got `llm_timeout_seconds` added to their fake-settings stubs. This was forced by the unconditional `s.llm_timeout_seconds` read.
- Rule 1: the correctness-review fixes in 85c34bbc. Research models now use the run-budget timeout (finding scored 75). The comments no longer claim a total-duration bound or a 600s prior default (findings scored 75 and 50). The SC-2 test is pinned to its field (a task-review Important).
- Rule 2: added a `timeout=` keyword to `get_agent_llm` and `get_llm`. It is additive, and existing callers are unchanged.

### Intent Findings

- E001 (drift and excess): the research models use a 600s run-budget timeout through a new optional `timeout=` keyword argument, instead of only the global 120s. The owner chose A (keep it) on 2026-09-26.

### Advisory Findings

Correctness findings scored below 75. They are not fixed; they are recorded here for the human.
- llm.py:55, score 50. The 120s bound also covers time-to-first-token of a reasoning model, and a timeout is retried 3x by LLM_RETRY, which means 3x prompt cost. On the dev DB the max chat call is 31s. `LLM_TIMEOUT_SECONDS` can be raised if this is seen.
- config.py:130, score 50. A blank or 0 `LLM_TIMEOUT_SECONDS` fails at startup, and there is no opt-out. This matches the other `gt=0` settings, and `.env.example` now says it must be > 0.
- config.py:130, score 50. `gt=0` accepts a value below 1ms, which google_genai rounds to 0ms.
- llm.py:55, score 0. The claim that google_genai `max_retries=0` means 5 retries was disproved: google-genai normalises `attempts=0` to 1.
- Unmodified lines, scored 0 by rule, all now reachable because calls can time out:
  - `date_tools.py:69` folds a transient timeout into a permanent ToolException.
  - `streaming/mapper.py:149` drops the retried `synthesize` message after a mid-stream timeout.
  - `core/embeddings.py:19` `OpenAIEmbeddings` still has no timeout.
- `research/agent.py` calls `get_settings()` even when a test injects both `llm` and `grader_llm`. It is harmless (re-review note).
- A true total-duration cap (for example `asyncio.timeout` around a node) would be a new control-flow mechanism (Rule 4). It is out of scope.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit: default 120 / override / explicit wins / all SDK profiles / research override | `cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_timeout.py -q` | 0 | 8 passed | SC-1 |
| unit: non-positive timeout rejected on the right field | `cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_timeout.py -q -k invalid` | 0 | 2 passed | SC-2 |
| unit: existing LLM client tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/clients -q` | 0 | 35 passed | SC-3 |
| lint | `cd apps/api && ruff check app scripts` | 0 | All checks passed | SC-4 |

### Not auto-verified

- Real-provider behaviour: no live call was made to confirm that a stalled stream raises at 120s. The kwarg acceptance was checked by constructing all three SDK clients (it reached provenance), but not by an actual timeout.
- The 120s default is sized from chat steps only (the dev DB has 777 steps; research steps may be absent). The research path is decoupled by the 600s override.
- Full suite: 3135 passed at 1e40dd84 and 3137 passed at 85c34bbc. It is not a Verify row, because the harness forbids whole-suite rows.

### Rollback

- `git revert --no-edit 31dbcc98..85c34bbc`. Alternatively set `LLM_TIMEOUT_SECONDS` high (e.g. 3600) to neutralise it without a deploy of code. There is no schema or data change.

### Harness-Delta

- none
