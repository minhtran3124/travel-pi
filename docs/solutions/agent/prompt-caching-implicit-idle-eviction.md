---
problem_type: knowledge
module: agent/prompts
tags: prompt-caching, openai, cached-tokens, prompt-cache-retention, system-prompt, prefix, ground-current-date, idle-eviction, measurement, gpt-5.4-mini
severity: critical
applicable_when: Before any prompt-caching, cache_control, prompt_cache_retention or system-prompt-prefix change, when a review or doc claims caching is off, or when a turn's token cost looks higher than expected.
affects:
  - apps/api/app/agents/state.py
  - apps/api/app/agents/supervisor.py
  - apps/api/app/agents/subagents/_base.py
  - apps/api/scripts/cache_hit_report.py
  - apps/api/scripts/probe_cache_retention.py
  - apps/api/app/repositories/agent_run.py
supersedes: null
confidence: high
confirmed_at: 2026-09-10
---
## Applicable When

Before changing anything about prompt caching or the order of the agent system prompt, and any
time a review, a code comment or a doc asserts caching is on or off. The 2026-09-02 deep review
said "prompt caching chưa bật" on the strength of a comment in `app/core/pricing.py`; the data to
refute it was already being recorded per LLM step and nobody had read it.

## Pattern

**OpenAI prompt caching is implicit and already on in this app.** On the dev database (166 turns,
3–10 Sept 2026) it hit 71.9% overall — specialists 75.8%, supervisor 49.4%. Three nodes report 0%
and always will: `reflection`, `synthesize` and `summarize` send prompts under OpenAI's
1,024-token cacheable minimum.

**The misses are idle eviction, not prefix instability.** Supervisor hit rate by gap since the
previous run: under 5 min 94/98, 5–15 min 4/6, 15–60 min 2/9, over 60 min **0/17**. That is the
documented default `in_memory` retention (5–10 minutes idle, up to an hour). Only 2 of 30 misses sat
at the day rollover, which is all the date-note position ever cost.

**`prompt_cache_retention="24h"` does not fix it on `gpt-5.4-mini`.** The API accepts and validates
the parameter (a bad value returns HTTP 400 naming it), but a two-armed A/B after a true 87-minute
idle gap read zero cached tokens in **both** the 24h arm and the default control. That matches
`-mini` models being absent from OpenAI's extended-retention list. On the current model no
configuration setting fixes idle-gap misses; only a model on that list or a keep-warm ping would.

**Prefix order still matters for correctness.** The date note is now the last block of every agent
system prompt (`ground_current_date` appends, and is applied outermost at both call sites), so the
stable blocks — style, agent prompt, profile, instructions, trip snapshot, summary — come first.

## How to Use

Measure before changing anything. From `apps/api/` with `DATABASE_URL` set:

```sh
../../.venv/bin/python -m scripts.cache_hit_report --since 7d
../../.venv/bin/python -m scripts.cache_hit_report --since 24h --node supervisor --min-ratio 0.4
```

It reports per node and model: calls, input, cached, **uncached tokens** and **missed calls** —
two different things; the diagnosis above is about missed calls. `--min-ratio` gates on the overall
ratio only, because sub-floor nodes legitimately report 0%.

To test a retention claim (for example after changing the default model), use the two-armed probe.
Seed, wait more than an hour without touching the cache, then check once:

```sh
../../.venv/bin/python -m scripts.probe_cache_retention --seed --model <model>
# wait > 60 minutes
../../.venv/bin/python -m scripts.probe_cache_retention --check
```

The verdict is one of `RETENTION-WINS`, `TIE`, `BOTH-MISS`, `CONTROL-ONLY`.

## Gotchas

- **A one-armed retention probe proves nothing.** A 24h-only hit at 21 minutes idle sits inside the
  default policy's own documented window. Any retention claim needs a control arm and a gap past 60
  minutes.
- **A cache read refreshes the entry.** Every check restarts the idle clock, so a naive re-check
  looks like it succeeds forever. The probe stamps an attempt marker *before* its first call, so a
  crashed or partial check still spends the experiment — otherwise arm one's refresh makes a re-run
  print a false `RETENTION-WINS`, the one verdict that would ship code.
- **Verify the seed landed.** A write that never landed looks exactly like expiry at check time.
- **Two arms make four cells**, including only-the-control-hits (`CONTROL-ONLY`). Naming three
  lets the fourth fall through a decision rule.
- The attempt marker is claimed by read-then-write, not atomically, but the window is only the
  in-process gap before the marker is saved — no model call sits inside it. Two checks would have to
  start within a fraction of a millisecond. Add an `O_EXCL` lock only if the probe ever runs from
  automation.
- Re-reading a value every turn does not break the cache — the cache keys on bytes. The trip
  snapshot is one sentence of title and city, so it only breaks the prefix when either changes.
- The Docker `api` container bind-mounts the main checkout. Measure or evaluate a branch from its
  own worktree, not inside the container.

## Related

- docs/solutions/agent/eval-golden-notes-are-not-metrics.md
- docs/solutions/agent/planner-search-first-save-later.md
- specs/prompt-caching-system-prefix/SUMMARY.md
