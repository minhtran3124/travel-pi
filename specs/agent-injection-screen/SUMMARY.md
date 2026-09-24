# agent-injection-screen — Summary

Lane: high-risk
Confidence: medium
Reason: Hard gates `external-provider` (a new hosted decision-model API, TypeSafe Jev, with a new secret `TYPESAFE_API_KEY`; called over httpx, no manifest change) and `audit/security` (a prompt-injection filter on untrusted third-party text is a security control; with the hosted option, fetched web content leaves the box to a new vendor). Direction is clear (screen external content before it becomes a ToolMessage); the provider fork and flag policy decided by the owner at intake (E001 = A Jev hosted, E002 = B warning-wrap).
Flags: external-provider, audit/security, external systems, existing behavior (web tool output gains attributes in enforce mode), weak proof (no injection corpus in eval yet; classifier is non-deterministic across versions), multi-domain (tools + service + config + prompt)
Affects: app/core/config.py (mode/key/model/threshold settings); app/tools/web_search_tools.py (`<web_result>` attributes, PR #227); new app/services/injection_screen_service.py (httpx, no new dependency); app/prompts/concierge/v15.md + active.yaml; new scripts/injection_screen_smoke.py; tests. RAG, research agent, eval goldens and requirements are out of scope (design.md §1)
Input-type: new spec
Route: brainstorming ✅ design.md (2026-09-24, reviewer approved) → xia2 Deep ✅ research-brief.md (2026-09-24: raw httpx POST, no SDK; Noul has no confidence field; 529 → unavailable; PR #230 overlap) → writing-plans ✅ PLAN.md (2026-09-24, 5 tasks / 3 waves, reviewer approved) → using-git-worktrees → subagent-driven-development → correctness/intent review → PR
Escalate: no (E001–E002 decided 2026-09-24: A hosted Jev, B warning-wrap)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> make the deep research for https://www.langchain.com/blog/building-a-harness-with-jev
> thinking can we apply it to current project to improve performance or reduce cost
>
> nếu bắt buộc phải dùng thì apply dc ở use case nào?
>
> ok, viết 4 cái trên xuống phần research . sau đó run /feature-intake cho cai 1 truoc

Use case 1 as recorded in `specs/jev-harness-research/research-brief.md`: after `search_web` /
`find_places_live` (PR #227) and the RAG retriever return, classify each page/chunk with a
System One decision model (Jev via `langchain-typesafe`, or self-hosted Laya) using a Noul
"does this passage contain instructions aimed at the AI assistant?", and drop or warning-wrap
flagged content before it becomes a ToolMessage.

## What changed

Intake only. No code change yet.

### Rationale

Owner chose hosted Jev (E001 = A) and warning-wrap (E002 = B): no local model weights in the py3.12 image, and no page is ever lost to a false positive; the concierge prompt gains a rule to ignore instructions inside flagged blocks.
Research context: `specs/jev-harness-research/research-brief.md`. Existing defences the screen
sits behind: HTML-escaped `<web_result>` blocks with capped snippets (PR #227), store-layer
memory poisoning guard and `<traveller_memory>` wrapping (PR #214). PR #214 deferred exactly this
item as E001 (RAG / tool-output wrapping).

### Alternatives considered

- Deterministic regex/keyword screen (no model): cheapest, zero vendor, but low recall on
  paraphrased instructions; can still ship as the always-on first layer.
- `gpt-5.4-nano` yes/no call per page: no new dependency, ~$0.0002–0.0005 per page but ~1 s
  latency per item on the tool path; fallback if neither Jev nor Laya is acceptable.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake shape | `python .claude/scripts/verify_summary.py --lane agent-injection-screen` | | run at intake | |

### Not auto-verified

- none yet (no implementation claims)

### Rollback

- `git revert <sha>` once code lands; the feature ships behind an off-by-default flag.

### Harness-Delta

- none
