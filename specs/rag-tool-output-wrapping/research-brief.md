# rag-tool-output-wrapping — Research Brief

Depth: **Deep** (from intake lane `high-risk`). Re-run with evidence: no upgrade needed, nothing
lowers it. No waiver requested.

External surface: **yes** — the design depends on version-specific behaviour of
`langgraph.prebuilt.ToolNode` (its return shape, and `msg_content_output`'s serialization), so
version-matched official docs are required by `rules/research-depth.md` §Coverage even though no
dependency is added or upgraded.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | use the built-in `awrap_tool_call` hook on `ToolNode`, at the existing `build_subagent` seam |
| **Why this is the lightest credible path** | langgraph 1.2.6 already exposes a per-tool-call interception hook on `ToolNode` itself. Passing it in both construction branches covers all five specialists and every registered tool, and — because it runs per call, before results are assembled — it removes the need to handle the mixed `Command`/dict return shape at all. |
| **Confidence** | 90% — the hook was verified by executing it against a compiled one-node graph in this repo's venv, not inferred from documentation (which says the opposite). |
| **Next step** | `writing-plans` → PLAN.md from `design.md` §3–§5 |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm + Turborepo); this change is BE-only (`apps/api`) |
| Primary language + runtime | Python 3.14 local venv / 3.12 in Docker |
| Frameworks / platforms | FastAPI, LangGraph 1.2.6, langchain-core 1.4.8, pydantic 2.13.4 |
| Relevant packages | `langgraph.prebuilt.ToolNode`, `langgraph.graph.MessagesState` / `add_messages` |
| Detectable versions | installed in the repo venv; no manifest change proposed |
| Important constraints | branch is based on the unmerged PR #214; stage and commit separately; prompt edits need an `active.yaml` bump; `make test` (SQLite) |

---

## Feature Understanding and Assumptions

- **Requested feature:** "hold on cho bọc mem của rag + tool" — wrap RAG and tool output the way memory was wrapped, completing the review bullet E001 deferred.
- **What success appears to mean:** text the assistant did not author arrives inside a labelled block, cannot close that block, and the label is explained once in the prompt; nothing downstream that parses tool results breaks.
- **Assumptions from the request:** the two decisions taken in the same turn — separate spec/PR, and wrap every tool output rather than only the prose-carrying ones — plus the later decision to drop the nonce.
- **Assumptions still needing confirmation:** that no supported langgraph hook already does this (see Upstream, pending).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `ToolNode` is constructed in exactly one function, two branches: `app/agents/subagents/_base.py:278` (no fault policy) and `:283` (with `retry_policy`/`error_handler`), serving all five specialists. |
| `Local` | `_combine_tool_outputs` (`.venv/.../langgraph/prebuilt/tool_node.py:862-919`) returns `{"messages": [...]}` only when no output is a `Command`; otherwise a **list** mixing `Command` objects with `{"messages": [ToolMessage]}` dicts. Three repo tools return `Command`: `clarification_tools.py:51`, `trip_tools.py:543`, `:579`. |
| `Local` | `msg_content_output` (`tool_node.py:309-336`) passes strings through and `json.dumps(…, ensure_ascii=False)` everything else, so `ToolMessage.content` is always a string at the seam — and stripping `<`/`>` from a serialized JSON string is JSON-safe (neither char is JSON syntax nor part of an escape). |
| `Local` | State is `MessagesState` (`app/agents/state.py:79`), reducer `add_messages`, which upserts by `id` — the reason the design wraps at the seam (messages are new there) instead of rewriting messages already in state. |
| `Local` | Five sites build a `ToolMessage` by hand, all inside a `Command`: `_base.py:151`, `clarification_tools.py:55`, `trip_tools.py:547`, `:583`, `retry.py:226`. Three carry `status="error"`. |
| `Local` | Content consumers that would see wrapper text: `memory/summarizer.py:80-82` (joins every message's content; feeds `state["summary"]`, re-injected into every later system prompt) and `eval/adapters/langgraph_runner.py:101-103` (pairs tool output into `EvalToolCall.output`, which `evalkit/metrics/judged.py:180-196` turns into the judge's `retrieval_context`). Everything else reads metadata: `streaming/mapper.py:265-286` (`.artifact`/`.status`), `routers/agent.py:482-498` (filters to `AIMessage`), `agents/nodes.py` (name/status). |
| `Local` | `app/data/` contains no angle brackets in prose (`grep -rn "[<>]" apps/api/app/data/` → three hits, two `<` comparison operators and one `<name>` placeholder in a comment), so sanitization costs first-party catalog content nothing. |
| `Local` | `docs/solutions/agent/sync-node-breaks-async-only-tools.md` — a sync node in this exact position took whole tool batches down and every multi-intent golden scored on the broken path. The seam must be `async def`. |
| `Local` | `docs/solutions/agent/reflection-humanmessage-language-flip-decisions.md` — internal/control text injected into `state["messages"]` must not be shaped like traveller input; relevant because this change edits message content rather than adding messages. |
| `Local` | `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md` and `langgraph-thread-reset-and-prompt-reload.md` — a new prompt version without the `active.yaml` bump is a silent no-op, and the prompt is resolved at graph build time. |
| `Upstream` | OWASP's AI Agent Security cheat sheet states tool responses should be treated as untrusted data, not executable instructions, and recommends a per-request nonce in the delimiter because a static one is guessable once a transcript leaks. |
| `Upstream` | Research on structural role injection finds that **escaping** `<`/`>` neutralizes angle-bracket role delimiters while **stripping** is lossy — it silently corrupts legitimate payloads (JSON comparisons, code, markdown). No source endorses stripping over escaping. |
| `Upstream` | A tool-result-specific defence paper (AgentDojo-based) reports that parsing/classifying tool payloads beats plain delimiter-wrapping; wrapping alone is a weaker tier. |
| `Docs` | Microsoft's spotlighting work (delimiting / datamarking / encoding) measured indirect-injection success dropping from >50% to <2% — but for **documents in a prompt**, not tool results specifically. Delimiting is the cheapest and weakest of the three variants. |
| `Docs` | LangChain middleware docs describe `wrap_tool_call` only in the `create_agent` factory context, with no mention of a hand-built `StateGraph`. **This contradicts the installed source** — see Docs Findings. |
| `Local` | langgraph 1.2.6 as installed exposes `wrap_tool_call` / `awrap_tool_call` as **constructor parameters of `ToolNode` itself** (`tool_node.py:755-756`, stored `:777-778`, invoked `:1055` sync and `:1207` async), receiving a `ToolCallRequest` plus an `execute` callable and returning `ToolMessage | Command` — per tool call, before `_combine_tool_outputs` assembles anything. |

---

## Local Findings

- **Relevant files:** `app/agents/subagents/_base.py`, `app/agents/state.py`, `app/tools/rag_tools.py`, `app/tools/_base.py`, `app/memory/summarizer.py`, `app/memory/guard.py` (the prior art), `app/core/text.py`, `app/prompts/communication_style/`, `eval/adapters/langgraph_runner.py`, `evalkit/metrics/judged.py`, plus tests under `tests/agents`, `tests/tools`, `tests/eval`.
- **Existing abstractions / extension points:** the single `build_subagent` seam; `app/core/text.py` as the neutral home for text primitives; the prompt registry's versioned files + `active.yaml` pointer.
- **Conventions worth preserving:** best-effort agent paths never break a turn; `status` and `artifact` on a `ToolMessage` are load-bearing for reflection and the SSE panel; tool results are never persisted, so this is a prompt-shaping change only.
- **What can likely be reused:** the bracket-strip idea from `app/memory/guard.py` (as a primitive moved to `app/core/text.py`), and the wrapping vocabulary already established by `<traveller_memory>` in `app/agents/state.py`.
- **What appears missing locally:** any labelling or escaping of tool/RAG content — searched `apps/api/app/` for `<untrusted|<tool_result|<document|<rag|<retrieved|<external` and for `untrusted|data, not instructions|prompt injection|sanitiz`; the only hits are the memory subsystem and PII redaction.

---

## Upstream Findings

Gathered by a web-research subagent; takeaways are as reported by that agent — URLs were not
re-fetched by the orchestrator. Sources listed in the Source Pack.

- **Repositories / pages inspected:** OWASP AI Agent Security cheat sheet; Microsoft spotlighting
  (blog + paper); LangChain middleware docs and a DeepWiki summary of the middleware architecture;
  a langgraph GitHub issue on the heterogeneous `ToolNode` return shape; two arXiv papers (structural
  role injection in templated prompts; tool-result parsing as an injection defence).
- **Pattern already present upstream:** labelling untrusted content with delimiters is the
  established practice, and treating **tool responses** as untrusted is explicit OWASP guidance —
  this change is not inventing a convention.
- **What it refines in this design:**
  1. **Escaping beats stripping.** Escaping `<`/`>` breaks the tag-injection vector just as stripping
     does, without destroying legitimate payload content. Stripping is lossy and unrecoverable. This
     is why D4 escapes rather than strips.
  2. **A static delimiter is guessable once leaked.** OWASP recommends a per-request nonce. This
     design deliberately has none (three defects traced to the nonce — see `design.md` §6); the
     residual is recorded rather than hidden, and escaping removes the payload's ability to emit a
     literal `<` at all, which is what the nonce was protecting.
  3. **Delimiting is the weakest spotlighting variant**, and the headline >50%→<2% figure is for
     documents in a prompt, not tool results. Treat this change as one layer, not a solution.
- **Upstream gaps / uncertainties:** no published numbers for this exact pattern's effect on
  tool-use accuracy, over-refusal or token cost; at least one study found spotlighting *increased*
  attack success for one model, so the effect is model-dependent and wants a smoke eval rather than
  an assumption.

---

## Docs Findings

- **Official sources checked:** LangChain middleware documentation (`wrap_tool_call`), the langgraph
  `ToolNode` API reference, and the installed 1.2.6 source in this repo's venv.
- **Version-matched vs latest-stable:** the installed source is the authority here; the hosted docs
  describe the current library line without pinning to 1.2.6.
- **A documentation/source contradiction worth recording.** The middleware docs present
  `wrap_tool_call` exclusively as a `create_agent` concept, and a community summary states plainly
  that a hand-built `StateGraph` would have to implement such behaviour itself. The **installed
  source disagrees**: `ToolNode.__init__` accepts `wrap_tool_call` / `awrap_tool_call` directly
  (`tool_node.py:755-756`), independent of `create_agent`. The design follows the source, because
  the source is what runs — verified by executing the hook against a compiled one-node graph rather
  than trusting either document.
- **Return shape is undocumented as a contract.** That `ToolNode` returns a list mixing `Command`
  objects with `{"messages": […]}` dicts is inferable only from source plus an open GitHub issue; no
  narrative doc states it. With the per-call hook this design no longer depends on that shape, which
  removes the exposure — but the version stays pinned and the behaviour stays covered by tests.
- **Caveats:** a hook that is undocumented for this usage can change between minor versions without
  a deprecation note; that risk is recorded in the design.

---

## Recommendation

- **Primary recommendation:** build the wrapper at the `build_subagent` seam, per `design.md`.
- **Why this is the lightest credible path:** one function, two branches, covers five specialists and every registered tool; the content is already a string at that point; no dependency, schema or contract change.
- **Why the next-best alternative lost:** a rewriting node on the `tools → assistant` edge must echo each message's `id` for `add_messages` to upsert rather than append, and preserve `status`/`artifact` by hand. Per-tool wrapping is ~20 sites and silently excludes tools added later.
- **What would change this recommendation:** a supported langgraph post-tool hook (pending Upstream), which would replace the hand-rolled seam.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - The seam must be `async def` (recorded failure); a sync node here previously took whole tool batches down.
  - The list return shape (mixed `Command`/dict) must be handled or fan-out turns silently skip wrapping.
  - Stripping `<`/`>` from every tool result mangles traveller-authored `notes` in the model's view (accepted, recorded in design §7).
  - Error messages stay unwrapped and unsanitized by design, so provider error bodies still reach the model unlabelled.
  - The prompt is resolved at graph build time, so the `communication_style` v9 bump needs a rebuild before any live check.
- **Evidence gaps:** whether wrapping changes tool-use behaviour in practice can only be seen with a real model (`make eval-smoke`), not the FakeLLM suite.
- **Version uncertainties:** none — no dependency change; the langgraph behaviours relied on were read from the installed 1.2.6 source.
- **Follow-up questions for the user:** none blocking.

---

## Source Pack

- **Local files read:** `apps/api/app/agents/subagents/_base.py`, `apps/api/app/agents/state.py`, `apps/api/app/agents/nodes.py`, `apps/api/app/agents/retry.py`, `apps/api/app/tools/rag_tools.py`, `apps/api/app/tools/_base.py`, `apps/api/app/tools/_idempotency.py`, `apps/api/app/tools/clarification_tools.py`, `apps/api/app/tools/trip_tools.py`, `apps/api/app/memory/{guard,summarizer,extractor}.py`, `apps/api/app/core/text.py`, `apps/api/app/exceptions.py`, `apps/api/app/streaming/mapper.py`, `apps/api/app/routers/agent.py`, `apps/api/eval/adapters/langgraph_runner.py`, `apps/api/evalkit/metrics/{judged,trajectory}.py`, `.venv/.../langgraph/prebuilt/tool_node.py`, `docs/solutions/agent/{sync-node-breaks-async-only-tools,reflection-humanmessage-language-flip-decisions,supervisor-active-yaml-is-a-pointer}.md`, `specs/memory-poisoning-hardening/{design,SUMMARY}.md`
- **Upstream repositories or pages checked:**
  - https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
  - https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py
  - https://github.com/langchain-ai/langgraph/issues/8924 (heterogeneous return shape)
  - https://deepwiki.com/langchain-ai/langchain/4.1-agent-creation-and-middleware-architecture
  - https://mlflow.org/articles/prompt-injection-defense (spotlighting summary)
  - arXiv 2403.14720 (spotlighting), arXiv 2606.18120 (structural role injection), arXiv 2601.04795 (tool-result parsing)
- **Official docs domains or pages checked:**
  - https://docs.langchain.com/oss/python/langchain/middleware/custom
  - https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolNode
  - the installed `langgraph` 1.2.6 source in this repo's venv (the authority for this change)

---

## Evidence Boundary

> Confirmed from artifacts: the seam and its two branches; the `ToolNode` return shapes and string
> serialization; the reducer; the five hand-built sites and their `Command`/status split; the two
> content consumers and the metadata-only readers; the absence of any existing labelling; the
> absence of angle brackets in seeded catalog prose.
> Inferred from patterns: that wrapping will not materially change tool-use behaviour — unverified
> until a real-model run.
> Not checked: real-model behaviour; whether a supported langgraph hook exists (pending Upstream).
