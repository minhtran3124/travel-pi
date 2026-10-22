# memory-poisoning-hardening — Research Brief

Depth: **Deep** (from intake lane `high-risk`; audit/security hard gate). Re-run with evidence:
no upgrade needed (already Deep); no signal lowers it. No waiver requested.

External surface: **none** — no new/upgraded dependency, no external system; relies only on
APIs already used in-repo (LangGraph `BaseStore`, `ToolNode` injection, pydantic `Literal`).
Upstream search still ran (Deep requires it) for defensive patterns.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | build (small, local) on existing extension points — no library |
| **Why this is the lightest credible path** | Every memory write already funnels through three `upsert_*` functions and every read through six store helpers, so one pure guard module at that layer covers all paths; no maintained library offers deterministic memory-write validation for LangGraph stores. |
| **Confidence** | 85% |
| **Next step** | `writing-plans` → PLAN.md from `design.md` §3–§5 |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm + Turborepo); this change is BE-only (`apps/api`) |
| Primary language + runtime | Python 3.14 local venv / 3.12 in Docker |
| Frameworks / platforms | FastAPI, LangGraph 1.2.6, langchain-core 1.4.8, pydantic 2.13.4 (installed in `.venv`) |
| Relevant packages | `langgraph.store` (`BaseStore`, `InMemoryStore`, PostgresStore), `langgraph.prebuilt.ToolNode` |
| Detectable versions | `apps/api/requirements.txt:12` pydantic `>=2.6,<3`; LangChain stack in `requirements-ai.txt` |
| Important constraints | stage and commit separately; prompt edits need `active.yaml` bump; `make test` (SQLite) + `make test-docker`; tests use FakeLLM |

---

## Feature Understanding and Assumptions

- **Requested feature:** close review §1 "Memory poisoning qua prompt injection" (`docs/reviews/2026-09-15-threat-intel-review.md`).
- **What success appears to mean:** injected meta-instructions are never persisted and, if already persisted, never reach the prompt; memory in the prompt is delimited as data; a real eval metric fails if injected text is stored.
- **Assumptions from the request:** decisions E001/E002 (ESCALATIONS.md) and B1–B4 (design.md §2).
- **Assumptions still needing confirmation:** none blocking (see Follow-up).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | Only direct `store.put` calls in `app/` + `scripts/` are inside `upsert_preference/instruction/episode` (`store.py:131,186,216`) — searched `grep -rnE "\.a?put\(|\.a?batch\(" app scripts`. Store-layer guard covers every write. |
| `Local` | Write callers: `extraction_runner.py:75,83,96`, `memory_tools.py:76` (grep `upsert_*` over `app`). |
| `Local` | MCP does **not** expose memory tools: tools with a `store` param are skipped (`app/mcp/server.py:51-53`). No third write path. |
| `Local` | `app/core/text.py:20` `fold_diacritics` — stdlib-only, maps `đ→d` + NFD strip; reusable for the VI blocklist. |
| `Local` | `app/agents/guardrails.py` is PII-only (card masking) — nothing reusable for injection patterns. |
| `Local` | `evalkit/types.py` `Golden` (no memory fields; must be extended) and `Trace.meta: dict` (exists — carry stored memory there). |
| `Local` | `docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`: explicit `args_schema` must keep `InjectedState`/`InjectedStore` fields; assert schema via `tool.tool_call_schema.model_fields` (`model_json_schema()` raises on `BaseStore`); only a ToolNode integration path catches injection breakage. |
| `Local` | `docs/solutions/agent/eval-golden-notes-are-not-metrics.md`: a golden is a gate only if a declared metric fails when the behaviour breaks. |
| `Local` | `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`: new `vN.md` without `active.yaml` bump is a silent no-op. |
| `Upstream` | Published memory-poisoning exploits (SpAIware on ChatGPT memory; Windsurf) used **tool/web/file content** auto-persisted to memory, not the user's own turn → validates excluding ToolMessages from extractor input (design §3.6). |
| `Upstream` | Microsoft Spotlighting: delimiting cut indirect-injection success from >50% to <2% in their tests, but is explicitly probabilistic → wrapping is one layer, not the boundary. |
| `Upstream` | Regex-blocklist bypass write-ups: paraphrase, encoding, multilingual and structured-data smuggling evade keyword filters → blocklist is a cheap tripwire; allowlist + length cap + wrapping are primary. |
| `Docs` | OWASP names Memory Poisoning as a distinct agentic threat (persistence across sessions); reference Agent Memory Guard does write-time policy checks plus size/rate anomaly detection. |
| `Docs` | LangGraph/LangMem long-term-memory docs describe extraction/storage but give no validation or injection guidance → nothing built-in to reuse. |
| `Inference` | Delimiters reduce but do not eliminate instruction-following of wrapped text; they are one layer beside write-time rejection. |

---

## Local Findings

- **Relevant files:** `app/memory/{store,extractor,extraction_runner}.py`, `app/tools/memory_tools.py`, `app/agents/{nodes,state}.py`, `app/prompts/memory_extraction/v5.md` + `active.yaml`, `app/core/text.py`, `app/exceptions.py`, `evalkit/{types.py,metrics/deterministic.py}`, `eval/adapters/langgraph_runner.py`, `eval/datasets/memory.json`, tests under `tests/memory`, `tests/agents`, `tests/tools`, `tests/api/agent`.
- **Existing abstractions or extension points:** `upsert_*` / read helpers in `store.py` (single choke point); `system_with_summary` (single prompt-assembly point); evalkit deterministic metric registry; `Trace.meta`.
- **Conventions worth preserving:** best-effort memory reads never break a turn; logs never carry secrets; explicit tool `args_schema` declares injected args; versioned prompts + CHANGELOG.
- **What can likely be reused:** `fold_diacritics`, `AppError`, `PROFILE_KEYS`, canonical keys already listed in extractor v5, `compiled.store` / `compiled.extract_memory_llm` for the eval adapter.
- **What appears missing locally:** any content validation on memory; any untrusted-data delimiter (review search: `grep -rnE "untrusted|<memory|data, not instructions"` over `app/prompts app/agents app/rag app/memory` → 0 hits); eval metrics that inspect stored memory.

---

## Upstream Findings

Gathered by a web-research subagent; sources listed in Source Pack. Takeaways are as reported
by that agent — URLs were not re-fetched by the orchestrator.

- **Repositories inspected:** OWASP Agent Memory Guard project; LangChain/LangMem memory docs; Microsoft MSRC spotlighting post + paper; Embrace The Red exploit write-ups; regex-bypass write-up.
- **Pattern or capability already present upstream:** write-time policy checks on memory (OWASP Agent Memory Guard); delimiting / datamarking of untrusted text (Microsoft Spotlighting). No drop-in library for LangGraph `BaseStore` validation.
- **Files, modules, or areas worth modeling:** Spotlighting's delimiting mode (matches `<traveller_memory>` + preamble); OWASP's split of write-time policy vs read-time check (matches B2/B4).
- **How closely the upstream pattern matches this repo:** close in principle; implementation must be local (store helpers are project code).
- **Any upstream gaps or uncertainties:** upstream recommends mitigations beyond this spec's scope — (a) user-visible memory review/delete, (b) human approval before memory writes, (c) write rate/size anomaly detection. Recorded as follow-ups below, not added to scope (E001/E002 bound it).

---

## Docs Findings

No external surface (no dependency added/upgraded, no external system, no newly relied-on
version-specific API) — official docs not required. Installed versions recorded in Repo Snapshot.

---

## Recommendation

- **Primary recommendation:** build a small pure guard module and enforce it at the store layer, per `design.md`.
- **Why this is the lightest credible path:** one choke point for writes (3 functions) and reads (6 helpers) is already there; the guard is ~stdlib regex + constants; no new dependency, no schema change, no migration (B4 read-side content filter).
- **Why the next-best alternative lost:** guard at each caller (B-alt) leaves future writers unguarded; a pydantic `MemoryItem` model covers parsing but not the read path; an LLM judge was ruled out by E002 (cost/latency, non-determinism).
- **What would change this recommendation:** a new memory writer that bypasses `store.py` (none today), or eval showing the delimiter preamble degrades personalisation on existing memory goldens.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - Over-blocking legit preferences → positive guard cases + positive golden (`design.md` §5).
  - Prompt change affects every agent turn → block order unchanged; `make eval-smoke` vs baseline.
  - Tool `Literal` key: unknown key now fails pydantic before the tool body; ToolNode error handling must turn it into a model-visible message (verify via a ToolNode integration test, not schema-only — per the args-schema lesson).
  - Test churn across ~8 test files that write non-canonical keys.
  - Concurrent branch adding `memory_extraction/v6.md` (`concurrent-branches-collide-on-prompt-version`).
- **Evidence gaps:** real-model behaviour of extractor v6 is only observable via paid/real eval runs; FakeLLM tests prove the guard, not the prompt.
- **Version uncertainties:** none (no dependency change).
- **Follow-up questions for the user:** none blocking.
- **Out-of-scope follow-ups surfaced by upstream (candidate specs, not this one):**
  - user-visible memory review / delete ("what do you remember about me");
  - human confirmation before persisting a standing instruction;
  - write rate / size anomaly detection on memory namespaces;
  - RAG / tool-output wrapping (already deferred by E001).

---

## Source Pack

- **Local files read:** `apps/api/app/memory/{store,extractor,extraction_runner}.py`, `apps/api/app/tools/memory_tools.py`, `apps/api/app/agents/{nodes,state,guardrails}.py`, `apps/api/app/mcp/server.py`, `apps/api/app/core/text.py`, `apps/api/app/prompts/memory_extraction/v5.md`, `apps/api/app/prompts/active.yaml`, `apps/api/evalkit/types.py`, `apps/api/eval/adapters/langgraph_runner.py`, `apps/api/eval/datasets/memory.json`, `docs/solutions/agent/{explicit-args-schema-breaks-tool-injection,eval-golden-notes-are-not-metrics,supervisor-active-yaml-is-a-pointer}.md`, `docs/reviews/2026-09-15-threat-intel-review.md`
- **Upstream repositories or pages checked:**
  - https://owasp.github.io/www-project-agent-memory-guard/
  - https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
  - https://www.microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks
  - https://arxiv.org/pdf/2403.14720 (Spotlighting)
  - https://docs.langchain.com/oss/python/langchain/long-term-memory
  - https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
  - https://embracethered.com/blog/posts/2025/windsurf-spaiware-exploit-persistent-prompt-injection/
  - https://thehackernews.com/2024/09/chatgpt-macos-flaw-couldve-enabled-long.html
  - https://dev.to/oopssec-store/prompt-injection-5-ways-to-bypass-a-regex-blocklist-on-an-llm-3626
- **Official docs domains or pages checked:** - none (local-only; no external surface)

---

## Evidence Boundary

> Confirmed from artifacts: all write/read paths and their callers (greps above); MCP exclusion of store tools; installed library versions; evalkit Golden/Trace shape; reusable helpers.
> Inferred from patterns: delimiter effectiveness is partial; extractor v6 wording will reduce but not eliminate bad extractions.
> Not checked: real-model extractor behaviour under v6 (needs eval run); production store contents (how many legacy rows would be filtered/truncated).
