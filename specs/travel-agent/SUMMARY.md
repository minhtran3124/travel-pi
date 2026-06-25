# SUMMARY — travel-agent

Lane: high-risk
Confidence: medium
Reason: New external dependency tree (LangChain/LangGraph/OpenAI/Langfuse/pgvector) plus
upcoming schema changes and new `/agent/*` public endpoints. Phase 0 itself (deps + config)
is the low-risk foundation; later phases carry the hard gates.

## Rationale

Add the AI travel-assistant agent layer per `PLAN.md` (agentic multi-agent on LangGraph,
provider-agnostic with OpenAI default). Phase 0 lays the foundation: pin the AI dependency
stack and add provider-agnostic LLM/agent settings that run zero-config (no key, no network)
so the existing suite and CI stay green.

## Alternatives

- OpenAI-only SDK (rejected — owner chose provider-agnostic `init_chat_model()` for easy
  provider swap + eval comparison; overrides the Anthropic assumption in `specs/llm-readiness`).
- Keep AI deps inline in `requirements.txt` (rejected — split to `requirements-ai.txt` so the
  large LangChain transitive tree is isolated and the core mock-API install stays lean).

## Progress

- **Phase 0 — Deps & config foundation: DONE**
  - 0.1 — AI deps added (`requirements-ai.txt`, `-r` from `requirements.txt`). Resolved on
    Python 3.14: langgraph 1.2.6, langchain 1.3.11, langchain-openai 0.3.34,
    langchain-anthropic 1.4.7, langfuse 4.12.0, checkpoint-postgres 3.1.0, pgvector 0.3.6.
  - 0.2 — `Settings` extended with LLM/agent fields (provider-agnostic, OpenAI default, no
    mandatory key, Langfuse disabled by default); `.env.example` updated.

## Deviations

- None. (Blast-radius hook warned config.py/.env.example/requirements*.txt are outside the
  *stale* active-plan pointer `specs/models-uuid-timestamp-base`; they are in scope for
  `specs/travel-agent` Tasks 0.1/0.2 — false positive from the stale pointer.)

## Notes

- langfuse resolved to 4.12.0 → use `from langfuse.langchain import CallbackHandler` (v4 path)
  in Phase 7, as already noted in PLAN Task 7.1.
- websockets downgraded 16.0 → 15.0.1 by the resolver; full suite stayed green (757 passed).

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Deps install + import smoke | `uv pip install -r requirements.txt && python -c "import langgraph, langchain, langchain_openai, langchain_anthropic, langfuse; from langgraph.checkpoint.sqlite import SqliteSaver; from langchain.chat_models import init_chat_model; from langfuse.langchain import CallbackHandler"` | 0 | import ok |
| Config tests (0.2) | `pytest tests/core/test_config_llm.py -q` | 0 | 7 passed |
| Full suite regression | `pytest -q` | 0 | 757 passed |
| Lint + format | `ruff check … && ruff format --check …` | 0 | clean |

### Rollback

- Revert code: `git revert <sha>` (Phase 0 commit).
- Remove AI deps: delete `requirements-ai.txt` + its `-r` line, then `uv pip install -r requirements.txt`.
