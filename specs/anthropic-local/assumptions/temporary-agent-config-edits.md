# Temporary edits to shared agent_config rows

PR #275, issue #270. Source: test:memory-cost.

## Assumption &middot; PR #275 &middot; issue #270</div><h1>Temporary edits to shared agent_config rows</h1></div><div class="card"><div class="lab">Context

The dashboard cases need saving rows (reflection, supervisor).

## Decision

Edited the rows briefly, then restored them to haiku-5-5 with blank effort and temperature. Restore was verified in the DB.

## Alternatives

Test only on a copy of the DB.

## Impact if wrong

Negligible. The edit reached the shared DB, but the shared server's config cache was not invalidated, so testers on 8000 were likely unaffected. At most a brief window where DB beats env.

## How to reverse

Already reversed. If a row drifts, set it back to haiku-5-5 with blank effort and temperature in the dashboard.

