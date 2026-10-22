# gh-146-synthesize-reply-language — Research Brief

Depth: **Standard** (intake lane normal → Standard; not reclassified). No waiver. External surface: **none** — no dependency, no external system, no version-specific API; the change reuses an in-repo helper. Official-docs search not applicable.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **reuse existing** — apply `with_reply_language(system, state)` (`app/agents/state.py:181`) inside `synthesize(state)`, the same call every sub-agent already makes (`subagents/_base.py:255`). |
| **Why this is the lightest credible path** | One import + one line in the closure; the guard is a pure function with an existing unit-test pattern (`tests/agents/test_state.py:278-310`) to copy. |
| **Confidence** | 90% |
| **Next step** | `writing-plans` (2 tasks: node change + new unit test). |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo; this change is `apps/api` only |
| Primary language + runtime | Python 3.14 locally, 3.12 CI |
| Frameworks / platforms | LangGraph 1.x graph (`app/agents/graph.py`), `langchain_core` messages |
| Relevant packages | `app/agents/nodes.py`, `app/agents/state.py`, `app/clients/llm.py` (`FakeLLM`), `tests/agents/` |
| Detectable versions | unchanged; no manifest touched |
| Important constraints | `rules/behavior.md` surgical edits; prompt text lives inline in `nodes.py` for this node (no registry entry) — design says do not move it |

## Feature Understanding and Assumptions

- **Requested feature:** the `synthesize` node (multi-intent turns) replies in the supervisor-detected conversation language, like every sub-agent. Issue #146: English turn `budget-ambiguous-en-02` got a Vietnamese synthesized reply 3/3 judged runs.
- **What success appears to mean:** the system message the synthesize node sends carries the `Reply in the traveller's own language: <lang>` directive whenever `state["language"]` is set; unchanged when unset; existing graph tests still pass.
- **Assumptions from the request:** the directive in the system message is what makes sub-agents comply (it is the only difference between them and synthesize today); no product decision needed on default language (`with_reply_language` is a no-op when undetected, by design).
- **Assumptions still needing confirmation:** none blocking. Whether the directive alone fixes the judged case is only provable with a keyed run (user spend) — recorded as not auto-verified.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/agents/nodes.py:161-201` — `make_synthesize_node(llm)` builds `system = SystemMessage(...)` **once, outside** the closure (line 170); `synthesize(state)` (line 179) reads `language = state.get("language", "en")` only to render a prose line in the `HumanMessage`, then `llm.invoke([system, HumanMessage(content=prompt)])` (line 193). The guard must therefore be applied **per call inside** `synthesize`, producing a per-state message, not by mutating the shared `system`. |
| `Local` | `app/agents/nodes.py:32` — `from app.agents.state import TravelAgentState` is the only import from `state`; `with_reply_language` must be added to it. |
| `Local` | `app/agents/state.py:181-210` — `with_reply_language(base: SystemMessage, state) -> SystemMessage`: returns `base` unchanged when `state.get("language")` is falsy, else a new `SystemMessage` with `base.content + "\n\nReply in the traveller's own language: {language} — …"`. Pure; no side effects. |
| `Local` | `app/agents/subagents/_base.py:251-255` — order is `system_with_summary(state, ground_current_date(system, tz))` then `with_reply_language(system_msg, state)`; the guard is the last transform before `invoke`. Synthesize has no summary/date grounding, so the guard is the only transform needed. |
| `Local` | `app/clients/llm.py:165-230` — `FakeLLM` scripts `responses` / `structured_responses`; `_generate(self, messages, …)` does **not** record the messages it receives. |
| `Local` | `tests/agents/test_state.py:222-310` — existing pattern: `class CapturingLLM(FakeLLM)` overriding `_generate` to stash `messages`, then asserting `"Reply in the traveller's own language: en" in captured["messages"][0].content` and the negative case when `language` is unset. Directly reusable for a node-level unit test without building the graph. |
| `Local` | `grep -rn "Combine the specialist\|Conversation language" tests/` → no test asserts the synthesize prompt text; `grep -rln make_synthesize_node tests/` → none. Graph-level tests (`tests/agents/test_multi_intent_routing.py:20-47`, `test_task_ledger.py`) exercise synthesize only via `build_graph(...)` with `main_responses=[…, "combined answer"]` and assert `current_flow == "synthesize"` — they remain valid after the change (the guard alters the system message, not the scripted reply). |
| `Local` | `git log -- app/agents/nodes.py` — most recent touch `1301b9e feat(agent): serve code-authored replies in the conversation language (#145)`: language handling was centralised for code-authored replies; the synthesize node was not included. |
| `Upstream` | none found (local-only change; no upstream pattern beyond the repo's own `_base.py`). |
| `Inference` | The prose line `Conversation language: {language}` in the human message is a weaker signal than a system-level directive; sub-agents with the directive pass `reply_language` in the same runs where synthesize fails, so the directive is the credible lever. |

## Local Findings

- **Relevant files:** `app/agents/nodes.py` (node), `app/agents/state.py` (guard), `app/agents/subagents/_base.py` (reference usage), `tests/agents/test_state.py` (test pattern), `tests/agents/test_multi_intent_routing.py` (graph-level coverage to keep green).
- **Extension points:** `with_reply_language` is the single reply-language guard; `make_synthesize_node(llm)` accepts any `BaseChatModel`, so a unit test can call `make_synthesize_node(CapturingLLM(...))(state)` directly with a hand-built state dict (`task_results`, `language`).
- **Conventions:** node factories return closures; system messages are `SystemMessage`; tests use `FakeLLM` and never hit the network.
- **Reusable as-is:** the guard, the `CapturingLLM` test idiom.
- **Missing locally:** the guard call in `synthesize`; a unit test for the synthesize node's outgoing messages.

## Upstream Findings

- **Repositories inspected:** none beyond this repo — the pattern is repo-internal (`_base.py`).
- **Pattern present upstream:** n/a.
- **Match to this repo:** n/a.
- **Gaps:** none.

## Docs Findings

- none (local-only; no external surface).

## Recommendation

- **Primary:** reuse existing — inside `synthesize(state)`: `system_msg = with_reply_language(system, state)`; invoke with `[system_msg, HumanMessage(content=prompt)]`. Keep the prose line.
- **Why lightest:** one import, one line, one new test file; mirrors `_base.py:255` exactly.
- **Why the alternative lost:** registry-ising the inline prompt adds `active.yaml`/CHANGELOG/dashboard surface for no behavioural gain on this bug; a post-hoc language check adds an LLM call per multi-intent turn.
- **What would flip it:** if a keyed run after the fix still shows Vietnamese for `budget-ambiguous-en-02`, the cause is elsewhere (e.g. worker findings written in Vietnamese dominating the synthesis) and the prose/context would need reworking.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** none material; the guard is pure. A reflection REVISE re-enters `synthesize` (nodes.py:196-199 comment) and will get the same guard — desirable.
- **Evidence gaps:** real-model effect only provable with a keyed `--capability budget` run (user spend; optional SC).
- **Version uncertainties:** none.
- **Follow-up questions for the user:** none.

## Source Pack

- **Local files read:** `apps/api/app/agents/nodes.py` (lines 160-201, 219-242), `apps/api/app/agents/state.py` (175-215), `apps/api/app/agents/subagents/_base.py` (38-40, 248-260), `apps/api/app/clients/llm.py` (165-230), `apps/api/tests/agents/test_state.py` (278-310), `apps/api/tests/agents/test_multi_intent_routing.py` (20-47, 129-130), `specs/gh-146-synthesize-reply-language/{SUMMARY,design}.md`, git log of `nodes.py`.
- **Upstream repositories or pages checked:** none found
- **Official docs domains or pages checked:** none (local-only; no external surface)

## Evidence Boundary

> Confirmed from artifacts: node structure and line numbers; guard behaviour; `_base.py` ordering; `FakeLLM` does not capture messages; `CapturingLLM` idiom exists; no test asserts the synthesize prompt.
> Inferred from patterns: that the system-level directive is what makes sub-agents comply.
> Not checked: real-model behaviour after the fix (keyed run, user spend).
