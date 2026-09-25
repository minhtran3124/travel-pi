---
slug: user-simulation
doc: research-brief
created: 2026-09-25
depth: Deep (from intake lane high-risk; no upgrade needed)
---

# Research Brief — user-simulation

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | Build a thin orchestrator (design approach 1). Reuse the repo's existing pieces: the `/agent/stream` SSE contract, JWKS env overrides, `set_tier`, and the repositories. Adapt the user-simulator prompt patterns from tau-bench/tau2-bench. Do not adopt DeepEval's `ConversationSimulator`. |
| **Why this is the lightest credible path** | Every §9 unknown in the design was resolved by a real run: `claude -p` works on the subscription with about 1k tokens of overhead and returns `structured_output`, and the container reaches the host JWKS. Nothing in `app/` changes and no dependency is added. |
| **Confidence** | 85% |
| **Next step** | Apply the four design deltas below (§Recommendation), then run `writing-plans`. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm + Turborepo monorepo: FastAPI API (`apps/api`) and Next.js web (`apps/web`) |
| Primary language + runtime | Python 3.14 in the local `.venv`; Python 3.12 in the Docker image |
| Frameworks / platforms | FastAPI, SQLAlchemy 2, LangGraph, Alembic, Postgres (pgvector pg17) in Docker |
| Relevant packages | `httpx`, PyJWT (`jwt`), `cryptography`, `websockets` (all in the root `.venv`); `deepeval` 4.0.7 (in the `.venv`, not used); Claude Code CLI 2.1.282 |
| Detectable versions | Claude Code 2.1.282 (`claude --version`); deepeval 4.0.7 |
| Important constraints | No change to `app/` (D2). No new dependency. Separate Compose project name (memory `docker-test-compose-shares-project-name`). Node 24 for any Playwright script. |

## Feature Understanding and Assumptions

- **Requested feature:** virtual travellers from many places talk to the travel chatbot over HTTP. They are role-played by `claude -p` on the user's Claude Code quota, a live 2D lobby UI shows the sessions, and each batch produces a graded report, eval candidates, and sample data.
- **What success appears to mean:** `make sim-run N=2 PARALLEL=2` finishes against `api-sim`, the lobby animates both sessions live, and `report.md` lists per-session verdicts.
- **Assumptions from the request:** the chatbot stays on OpenAI, and all decisions in ESCALATIONS E001–E004 and design D1–D6 hold.
- **Assumptions still needing confirmation:** none block the plan. The quota headroom per batch is a runtime concern, and the new utilization guard handles it.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | A real `claude -p` run from a clean temp dir with `--system-prompt --tools "" --disable-slash-commands --strict-mcp-config --no-session-persistence --output-format json --json-schema`: exit 0, 4–5 s, `apiKeySource: "none"` (OAuth/subscription), `structured_output` held the schema object, input about 1,148 cache-creation tokens (Opus) or 1,044 (Sonnet). The whole system prompt is small, so user `~/.claude/CLAUDE.md` is not loaded. |
| `Local` | Without `--model`, the CLI used `claude-opus-5-5`, the user's default. Sonnet cost $0.0057 of equivalent spend per call, against $0.0145 for Opus. |
| `Local` | `--setting-sources ""` keeps OAuth working (exit 0) and cuts loaded plugins from 12 to 2 and agents from 51 to 5. |
| `Local` | The user settings have `"verbose": true`. With the default setting sources, `--output-format json` printed a JSON **array** of events; with `--setting-sources ""` it printed a single object. The parser must not depend on the shape. |
| `Local` | `--output-format stream-json --verbose` emits a `rate_limit_event` with `unifiedWindows.five_hour.utilization` (0.55) and `seven_day.utilization` (0.33), plus `resetsAt`. This is a live quota gauge. |
| `Local` | `docker run api-api:latest` → `urllib` GET `http://host.docker.internal:8766/.well-known/jwks.json` returned the host file (macOS Docker). |
| `Local` | The verifier fetches from `settings.resolved_jwks_url` (explicit `SUPABASE_JWKS_URL` wins) and checks `aud` and `iss` with RS256/ES256 (`app/core/auth.py:74-86`, `app/core/config.py:201-214`). Plain http is allowed. |
| `Local` | `users.user_id` is a `String` primary key (`app/db/models/user.py:14`), so `sim-<id>` subs are valid. |
| `Docs` | support.claude.com article 15036540, update of June 15: "we're pausing the changes to Claude Agent SDK usage … Claude Agent SDK, `claude -p`, and third-party app usage still draw from your subscription's usage limits." |
| `Docs` | code.claude.com Agent SDK overview: the ban is on third-party developers *offering* claude.ai login or rate limits in their products. A developer scripting their own login is not what it describes. |
| `Docs` | code.claude.com/docs/en/headless: `--bare` "doesn't use your subscription login"; structured output is in `structured_output`. |
| `Upstream` | tau-bench `tau_bench/envs/user.py`: a `###STOP###` stop token, one line at a time, reveal information gradually, never make up missing details. tau2-bench adds the `###TRANSFER###` and `###OUT-OF-SCOPE###` tokens and separates persona guidelines from the scenario. |
| `Upstream` | DeepEval 4.0.7 `ConversationSimulator(model_callback, simulator_model, stopping_controller, max_concurrent, language)`. A custom `DeepEvalBaseLLM` could wrap `claude -p`. |
| `Inference` | The persona prompt stays under about 2k tokens after 8 turns, so resending the transcript each turn costs little. `--resume` is not needed. |

## Local Findings

- **Relevant files, modules, scripts, docs, tests:**
  - `app/core/auth.py`, `app/core/config.py` (JWKS and issuer overrides)
  - `app/routers/agent.py`, `app/schemas/agent.py`, `app/streaming/events.py` (SSE contract)
  - `app/agents/nodes.py:367` (the `plan_approval` interrupt)
  - `scripts/set_tier.py`, `app/repositories/{user,booking,trip}.py`
  - `docker-compose.yml`, `docker/entrypoint.sh`, `app/core/lifespan.py`
  - `eval/` and `evalkit/` (golden loader), `tests/conftest.py` (auth override pattern)
- **Existing abstractions or extension points:**
  - The env-only JWKS override.
  - `set_tier` upsert.
  - `BookingRepository.list_all` and `TripRepository.list_trips`, both scoped by user.
  - The Makefile delegation pattern already used for `eval-*`.
- **Conventions worth preserving:**
  - Run the Python code from `apps/api/` with the root `.venv`.
  - Put tests in `apps/api/tests/<domain>/`.
  - One parameter per line in multi-parameter signatures.
  - Minimal comments.
- **What can likely be reused:** everything above, plus the eval dataset loader to validate `golden_candidates.json`.
- **What appears missing locally:**
  - no HTTP client for `/agent/stream` (searched `scripts/`, `eval/`, `apps/web/playwright`);
  - no local JWT signer;
  - no WebSocket server.

## Upstream Findings

- **Repositories inspected:**
  - sierra-research/tau-bench
  - sierra-research/tau2-bench
  - langchain-ai/openevals (`create_llm_simulated_user`, `run_multiturn_simulation`)
  - confident-ai/deepeval 4.0.7 (installed source)
- **Pattern or capability already present upstream:** an LLM user simulator with a persona and a scenario, gradual information reveal, an explicit stop signal, and a turn cap.
- **Files, modules, or areas worth modeling:** the tau-bench user system prompt rules, and tau2's split between persona and scenario.
- **How closely the upstream pattern matches this repo:**
  - The conversation-loop idea matches closely.
  - None of them drive an SSE endpoint, emit live UI events, or handle a HITL interrupt followed by `resume`.
- **Any upstream gaps or uncertainties:**
  - The openevals signatures are known from a docs summary only.
  - The DeepEval docs mention a `persona` field that the installed 4.0.7 lacks.

## Docs Findings

- **Official sources checked:**
  - support.claude.com articles 15036540 and 11145838
  - code.claude.com Agent SDK overview
  - code.claude.com headless docs
- **Version-matched vs latest-stable status:** the CLI flags were checked against the installed 2.1.282 through `claude --help` and real runs.
- **Built-in capabilities that already support the feature:**
  - `--json-schema` with `structured_output`
  - `--tools ""`
  - `--setting-sources ""`
  - the `rate_limit_event` utilization gauge in stream-json
- **Current recommended APIs or workflows:** `claude -p` for scripts. `--bare` is recommended for CI but is incompatible with subscription billing, so it is not used here.
- **Important caveats, deprecations, or migration notes:**
  - The Agent SDK monthly-credit change is **paused**, so `claude -p` draws from the shared Claude plus Claude Code 5-hour and weekly limits. Interactive Claude use competes with a batch for the same quota.
  - The policy may change again, so the README must name the date it was checked (2026-09-25).

## Recommendation

- **Primary recommendation:** build a thin orchestrator. Apply these deltas to design.md:
  1. **§5.1 flags.** Add `--setting-sources ""` and `--model ${SIM_CLAUDE_MODEL:-sonnet}`; without `--model` the CLI would use Opus. Switch to `--output-format stream-json --verbose` and read the final `result` event's `structured_output`, plus the `rate_limit_event`. Never pass `--bare`.
  2. **§5.6 / §7 quota guard.** Before admitting a new traveller, check the latest `five_hour.utilization` and `seven_day.utilization`. If either is at or above `SIM_QUOTA_CEILING` (default 0.85), stop admitting, finish in-flight turns, and write a partial report. The UI header shows both gauges. This protects the user's interactive quota.
  3. **§5.2 persona prompt.** Adopt the tau-bench rules: one message per turn, reveal facts gradually, never invent facts that are not in the card, set `intent_done` only once the goal is met or clearly impossible, and write in the persona's language.
  4. **§5.1 parsing.** Tolerate both output shapes, the array of events and the single object. With stream-json, read line by line.
- **Why this is the lightest credible path:** every external unknown was confirmed empirically. The code needed is small, and none of it is in `app/`.
- **Why the next-best alternative lost:** DeepEval's `ConversationSimulator` could drive the persona through a custom `DeepEvalBaseLLM` wrapping `claude -p`. It still lost:
  - Its `model_callback` returns a whole turn, so live token and tool events would need a side channel.
  - It has no hook for the HITL interrupt and `resume` step.
  - Its default stopping controller makes an extra LLM judgment every turn, which costs more quota.
  - A turn cap and an `intent_done` field replace that controller for free.
- **What would change this recommendation:** a future policy change that stops `claude -p` from drawing on plan limits. The design would then need an `ANTHROPIC_API_KEY` path (`--bare`), which is a one-flag change in `claude_cli.py`.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - Quota contention with the user's own interactive work (the guard mitigates this).
  - A user-level SessionStart hook may still run under the default setting sources; `--setting-sources ""` avoids it.
  - `PyJWKClient` caches keys per URL; a fresh `kid` per batch triggers a refetch (design §5.3).
- **Evidence gaps:**
  - The exact wording of the Max plan limits page was not opened first-hand.
  - Haiku reported 0 cache-creation tokens, so caching behaviour differs by model. This is not load-bearing.
- **Version uncertainties:** the CLI flags may change between Claude Code releases. `claude_cli.py` checks `claude --version` and records it in the report.
- **Follow-up questions for the user:** none blocking.

## Source Pack

- **Local files read:**
  - `apps/api/app/core/auth.py`, `app/core/config.py`, `app/routers/agent.py`, `app/schemas/agent.py`, `app/streaming/events.py`
  - `app/db/models/user.py`, `app/repositories/{booking,trip}.py`, `scripts/set_tier.py`
  - `docker-compose.yml`, `docker/entrypoint.sh`, `app/core/lifespan.py`, `app/core/llm_providers.py`, `app/clients/llm.py`
  - `eval/README.md`, `apps/api/Makefile`
  - CLI evidence: `claude --help` and three `claude -p` runs (scratchpad `clean.*/out{1,2,3}`)
- **Upstream repositories or pages checked:**
  - https://github.com/sierra-research/tau-bench
  - https://github.com/sierra-research/tau2-bench
  - https://github.com/langchain-ai/openevals
  - https://deepeval.com/docs/conversation-simulator (plus the installed deepeval 4.0.7 source)
- **Official docs domains or pages checked:**
  - https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
  - https://support.claude.com/en/articles/11145838
  - https://code.claude.com/docs/en/agent-sdk/overview
  - https://code.claude.com/docs/en/headless

## Evidence Boundary

> Confirmed from artifacts:
> - OAuth/subscription billing for `claude -p` without `--bare`
> - the `structured_output` field
> - about 1k tokens of overhead per call
> - that `--setting-sources ""` works
> - the `rate_limit_event` gauge
> - host JWKS reachability from Docker
> - string user ids
> - the JWKS/issuer override precedence
>
> Inferred from patterns:
> - the transcript-resend cost after 8 turns
> - DeepEval unsuitability for live events (from its API shape, not from a prototype)
>
> Not checked:
> - the Max plan limits page first-hand
> - the behaviour when utilization reaches 1.0, the exact error text of a quota rejection from `claude -p` (the driver treats any `is_error` result carrying rate-limit status as `QuotaExhausted`)
> - openevals full signatures
