# prompt-caching-system-prefix — Design

Status: **approved by user 2026-09-10** (E001 → A, E002 → B; see `ESCALATIONS.md`).
Lane: high-risk (external-provider hard gate: a provider-SDK request parameter in `app/clients/llm.py`).

## 1. Problem, re-stated with numbers

The 2026-09-02 deep review (§6) said "prompt caching chưa bật". Intake on 09-08 refined that to "the
prefix is unstable because `ground_current_date` prepends a per-day/per-timezone note". Measurement
on 09-10 against the dev Postgres (`agent_runs` / `agent_run_steps`, 166 turns, 03→10 Sept) shows
both framings are off:

| Slice | Input tokens | Cached | Hit |
|---|---|---|---|
| specialists (`assistant` steps, gpt-5.4-mini) | 3,333,627 | 2,527,744 | **75.8%** |
| supervisor | 465,818 | 229,888 | **49.4%** |
| all runs | 4,329,915 | 3,111,552 | **71.9%** |

Supervisor hit rate by idle gap since the previous run: `<5 min` 94/98 hits · `5–15 min` 4/6 ·
`15–60 min` 2/9 · `>60 min` **0/17**. Misses have a median idle gap of 3,960 s; hits 27 s. Only 2 of
30 misses sit at the 23:58–00:01 UTC day rollover.

So: OpenAI **implicit** caching already works on today's traffic (the date note is identical for every
request in the same day and zone, so the prefix *is* stable within a day). The dominant miss cause is
**in-memory eviction after 5–10 minutes idle** — exactly what OpenAI documents for `in_memory`
retention. The date-note position is a second-order effect (day rollover + per-timezone prefix split).

## 2. Goals

1. **Keep the cached prefix warm across idle gaps** on the default OpenAI path — the only lever that
   addresses the measured misses.
2. **Put volatile text last** so the cache key never depends on the date or timezone — cheap,
   provider-agnostic, and OpenAI's own guidance ("timestamps … place those at the end").
3. **Make the hit rate a number anyone can re-run**, so the next caching decision starts from data.

Non-goals: Anthropic `cache_control` (E001 kept it out; nothing routes to Anthropic today);
`prompt_cache_key` routing (single-tenant traffic, no per-customer accounting needed); dashboard UI
for cache stats; any prompt `.md` change; touching the summarizer.

## 3. Decisions

### D1 — Date note becomes the *last* block of the system message

`ground_current_date(base, tz)` returns `base.content + "\n\n" + note` (today it returns
`note + "\n\n" + base.content`; its own docstring already says "base followed by the note", the code
never matched). Both call sites wrap it **outermost**:

```
supervisor:  ground_current_date(system_with_summary(state, base), tz)
_base.py:    ground_current_date(with_reply_language(system_with_summary(state, system), state), tz)
```

Resulting order: `[agent prompt] [profile · email · instructions · trip_context · summary ·
trip_facts · preferences] [reply-language pin] [CURRENT DATE …]`. Everything that is stable per
conversation now precedes the one thing that changes per day.

*Alternative rejected:* append the note to the base prompt only (before the per-turn fields). That
keeps the date "near the instructions" but breaks the prefix at the date for every day rollover
*before* the per-user fields, which are stable within a conversation. Recency at the very end also
helps the "never fall back to today, ask" rule land — the eval `dates` goldens are the guard.

### D2 (CONDITIONAL) — `prompt_cache_retention="24h"` on the direct OpenAI profile, settings-gated

**Gated on the >60 min A/B verdict per `ESCALATIONS.md` E003.** Waves 1–3 ship without it; the
wiring is a conditional wave that fires only on `RETENTION-WINS`. Both branches are pre-authorised,
so the verdict needs no further human decision.

Probe on 2026-09-10 (`gpt-5.4-mini-2026-03-17`, openai 2.44.0, langchain-openai 0.3.34, Chat
Completions): the server validates the parameter (`"bogus"` → HTTP 400 `invalid_value` naming
`prompt_cache_retention`), `24h` and `in_memory` are both accepted, and a 3.2k prefix reads 2,816
cached tokens on the second call.

**The A/B at 21 min idle tied** — `24h` HIT (3,328/3,577) and the `in_memory` control also HIT
(2,816/3,310). That is not a refutation but it is not support either: OpenAI documents `in_memory` as
"5 to 10 minutes of inactivity, **up to one hour**", so 21 min sits inside both windows. The only
gap that discriminates is **>60 min**, which is exactly the bucket where the dev data shows 0/17
hits. A longer A/B re-call decides D2's fate:

- both arms hit at >60 min → the default already retains that long; the parameter buys nothing here.
  D2 ships **dark** (flag default `None`) and the spec records that the remaining lever is a model
  change or a keep-warm ping.
- only `24h` hits → D2 is the fix for 28/30 measured misses and the flag default stays `24h`.

E003 replaced the earlier "ship the flag either way" stance: with the benefit unproven, putting a
provider-SDK parameter into the shared client buys nothing but risk, so the wiring waits for the
verdict. The flag shape stays as designed for the day the verdict flips.

Wiring: new `Settings.openai_prompt_cache_retention: str | None = "24h"` (validator: `24h`,
`in_memory`, or `None`/empty = do not send). In `_build_chat_model`, inside the existing
`if profile.sdk == "openai":` branch, **and only when no `base_url` resolved** (a base URL means a
gateway such as `clinepass`, whose proxy may reject unknown parameters):

```python
if resolved_base_url is None and s.openai_prompt_cache_retention:
    kwargs["model_kwargs"] = {"prompt_cache_retention": s.openai_prompt_cache_retention}
```

Anthropic / Gemini profiles never see the kwarg. Per-agent DB overrides are unaffected (they flow
through the same builder).

*Alternatives rejected:* rely on the org default (docs say non-ZDR orgs default to `24h` on listed
models — but `-mini` models are not listed and the observed eviction curve is the `in_memory` one);
per-agent DB field (over-scope for one boolean-ish knob).

### D3 — Hit-rate report as a script over `agent_run_steps`

`python -m scripts.cache_hit_report --since 7d [--node supervisor] [--min-ratio 0.5]` prints, per
`node × model`: calls, input, cached, hit %, and the miss count; plus the overall ratio. A new
repository method `AgentRunRepository.llm_steps_since(since)` supplies the rows (kind = `llm`), keeping
data access in the repository layer. `--min-ratio` exits 1 below the threshold so the number can gate.

### D4 — Retention proof as a two-phase script

`python -m scripts.probe_cache_retention --seed` sends two nonced ~3k-token prompts (one per
retention value, two calls each so the write lands) and stores nonces + timestamp;
`--check` re-sends both and exits 0 only when elapsed ≥ 15 min **and** the `24h` prefix reads cached
tokens. Each phase is one command under 60 s, so it can be an SC row; the wait is the operator's.

## 4. Expected outcome (honest)

- D2 is the only change that can move the measured 28/30 idle-gap misses, **and its benefit is
  unproven** — the 21 min A/B tied (see D2). Treat the expected saving as 0 until the >60 min A/B
  reports; the flag exists so that verdict can flip without another escalation.
- D1 removes the day-rollover and per-timezone prefix split (≈2/30 observed misses) and is
  standards-correct regardless.
- Cost side: cached input is billed at the provider's cached rate already priced in `pricing.py`
  (`cached_input`); `24h` retention carries no extra charge per the OpenAI docs.

## 5. Risks

| Risk | Mitigation |
|---|---|
| Moving the date note changes model behaviour on date questions | existing `test_ground_current_date_*` + `dates` eval goldens (`make eval-smoke` at phase acceptance) |
| Gateway profile rejects `prompt_cache_retention` | never sent when a `base_url` resolved (D2 guard) + unit test per profile |
| Future OpenAI model drops `in_memory` (docs: gpt-5.5+ accept only `24h`) | we send `24h`; flag can be emptied by env without a deploy of code |
| Dev traffic ≠ prod traffic | the report script makes the prod number a one-liner once prod has `agent_runs` |
