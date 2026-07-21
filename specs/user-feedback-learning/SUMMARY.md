# SUMMARY — user-feedback-learning

Lane: normal
Confidence: high
Reason: Research-only architecture work with no runtime, schema, public-contract, dependency, or
prompt mutation. Confidence is high because the current code path and official hot-path/background
patterns agree on the recommended shape.

## Rationale

The travel supervisor is an intent router, while memory learning is a cross-cutting lifecycle.
Travel-pi already moved memory extraction out of the graph and into post-response background tasks.
The selected design retains that seam, adds a deterministic policy/verifier between LLM candidates
and writes, and uses a hot path only for explicit remember/correct/forget commands.

## Alternatives

- Supervisor-routed `learning_agent` — rejected because learning is not a travel intent, may be
  skipped by routing, and adds latency/decision load to every turn.
- Terminal in-graph extraction node — rejected for the default path because the repo already removed
  it to avoid adding an LLM call to reply latency.
- Let each specialist manage memory — rejected as the sole mechanism because tool use is
  discretionary and policy would drift across specialists.
- Adopt LangMem immediately — rejected; its concepts validate the design, but the repo already has
  equivalent BaseStore and extraction seams.
- Direct online prompt optimization or weight training — rejected as unsafe and non-auditable from
  individual feedback; shared behavior changes belong behind offline eval and versioned deployment.

## Outcome

- Answered the core architecture question: no supervisor-routed memory specialist.
- Distinguished user memory, system improvement, and model training.
- Documented current source-of-truth code, including the stale `WORKFLOW.md` topology.
- Defined feedback events, memory candidates, write/conflict policy, privacy controls, eval gates,
  and a four-stage rollout.
- Identified a separate high-risk implementation boundary for new feedback persistence/API/UI work.
- Follow-up 2026-07-21 — synchronized `WORKFLOW.md` with the current parent graph, task ledger,
  fixed per-run context, background extraction, state/tool/model configuration, and known gaps.
  `WORKFLOW_DIAGRAM.md` remains intentionally untouched pending the next pass.

## Deviations

- None. Research-only; no implementation was attempted.

### Verify

| Check | Command | Exit | Notes |
|---|---|---:|---|
| Current memory seams | `rg -n "run_memory_extraction\|extract_memory_llm\|load_context_node\|MemoryKind" apps/api/app apps/api/tests` | 0 | Confirmed background write, graph model handle, recall, and namespaces |
| Focused memory tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_extraction_runner.py tests/memory/test_extractor.py tests/agents/test_preferences_injection.py tests/agents/test_checkpointer_selection.py -q` | 0 | 33 passed, 1 pre-existing Starlette deprecation warning |
| Official-source links | `rg -n "docs.langchain.com\|langchain-ai.github.io\|help.openai.com" specs/user-feedback-learning/RESEARCH.md` | 0 | LangGraph, LangMem, LangSmith, and OpenAI sources present |
| Architecture sections | `rg -n "Decision stack\|Write policy\|Target architecture\|FeedbackEvent\|MemoryCandidate\|Offline" specs/user-feedback-learning/RESEARCH.md` | 0 | Required decisions and models present |
| Markdown whitespace | `if rg -n '[[:blank:]]+$' specs/user-feedback-learning; then false; else true; fi` | 0 | No trailing whitespace in the new untracked research files |
| Workflow stale claims removed | `if rg -n 'mode × tier\|extract_memory → END\|current_flow=REVISE\|ctx\.model\|gpt-4\.1' WORKFLOW.md; then false; else true; fi` | 0 | Old in-graph extraction, request-mode, model-hint, and model-default descriptions removed |
| Workflow current anchors | `rg -n 'dispatch_next\|AFTER RESPONSE\|no .*extract_memory.* graph node\|BackgroundTask\|gpt-5-mini\|pending_flows\|awaiting_user' WORKFLOW.md` | 0 | Current topology, context, background extraction, and defaults documented |
| Workflow diff hygiene | `git diff --check -- WORKFLOW.md` | 0 | No whitespace errors |

### Rollback

- Research-only files can be removed by deleting `specs/user-feedback-learning/`; no runtime state or
  application behavior was changed.
