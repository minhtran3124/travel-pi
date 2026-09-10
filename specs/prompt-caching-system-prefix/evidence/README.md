# Evidence — prompt-caching-system-prefix

Durable copies of experiments whose originals lived in a session scratchpad.

## Date-rule A/B (`date_rule_probe.py`)

Tests whether the rules carried by `ground_current_date`'s note still hold after the note moved
from the front of every system prompt to the end (design D1). It exists because the planned gate —
the `dates` eval goldens — does not measure this: every date golden checks routing, reply language
and non-empty replies, and none would fail if the model silently used today's date.

Same script, two code versions, run 2026-09-10 on `gpt-5.4-mini-2026-03-17` through the eval
harness's production runner (DB agent config, premium context), k=3 per probe:

- `daterule_main_note_first.json` — `main` at `34f9920`, note FIRST (original order)
- `daterule_branch_note_last.json` — branch at `81c89f0`, note LAST

Re-run from any checkout (`OPENAI_API_KEY` and `DATABASE_URL` for the dev Postgres must be set):

    cd <checkout>/apps/api
    PYTHONPATH=. ../../.venv/bin/python <this dir>/date_rule_probe.py 3 <label> <out.json>

Verdicts are mechanical, no judge: a no-date probe is a VIOLATION if any search tool received a
date (the traveller gave none, so any date was invented); a relative-date probe is a VIOLATION if a
dated search ran without a `resolve_date` call.

## Prefix-cache before/after (`prefix_cache_ab.py`)

Measures the one thing design D1 changes, with OpenAI's own `cached_tokens`: whether the agent
system prompt's cached prefix survives a change of the date note (another timezone, or a new day).
Each checkout assembles the planner sub-agent's system message with its own real code
(`build_subagent`), captured exactly as the model receives it. Per timezone pair, the tz-A prompt is
sent to warm the cache, then the tz-B prompt, and `cached_tokens` is read on the tz-B call.

| Version | Note | Shared prefix | Cached on tz-B call |
| --- | --- | --- | --- |
| `main` 34f9920 | first | 43 / 18,205 chars | **0** / 4,373 tokens |
| branch bab0f0d | last | 17,597 / 18,205 chars | **3,840** / 4,373 tokens |

Both timezone pairs gave the same result. Results: `prefix_cache_main_note_first.json`,
`prefix_cache_branch_note_last.json`.

Why a same-day hit-rate comparison could not show this: within one day and one zone the note is
identical, so both orderings keep a stable prefix. The difference appears only when the note
changes, which the dev database — a single timezone — records only at the day rollover.
