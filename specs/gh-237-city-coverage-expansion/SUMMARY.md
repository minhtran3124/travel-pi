# gh-237-city-coverage-expansion — Summary

Lane: normal
Confidence: high
Reason: seed-data expansion across several data modules (existing behavior, multi-domain, weak proof). No hard gate: no schema change or migration (seed_all upserts with session.merge), no auth or public-contract change, and no new runtime dependency.
Flags: existing behavior, multi-domain, weak proof
Affects: apps/api/app/data/{cities,airports,hotels,places,tips,visa,countries,fx}.py, app/data/content_translations.vi.json; the synthetic flight and hotel services that read them; eval goldens and baselines that depend on seed data
Input-type: new initiative
Route: xia2 (Standard) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> Có thể check xem thành phố nào ko có trong dữ liệu thì cập nhật thêm. Tìm nguồn internet latest và update.

(Scope chosen by the user in answer to the follow-up questions: "Đông Bắc Á + quốc tế phổ biến" — about 20 cities: Osaka, Kyoto, Fukuoka, Sapporo, Busan, Jeju, Taipei, Shanghai, Beijing, Guangzhou, Paris, London, Lisbon, Rome, Sydney, Melbourne, Dubai, Istanbul, New York, Los Angeles; depth "Đầy đủ" — airports and routes, 6–8 real hotels, places, tips, visa/fx for new countries, and Vietnamese translations.)

> Nếu cần thì spawn subagent với haiku để tìm kiếm cho rẻ

## What changed

Intake only.

### Rationale

Both live user-simulation runs sent travellers to cities outside the 52-city inventory (Osaka, Lisbon), and the agent looped on empty searches (#237). Expanding the inventory in the existing seed format fixes the gap without any code or schema change. Web research runs on Haiku subagents to keep cost down, and the stronger model assembles and verifies the data.

### Alternatives considered

- Fix the agent behaviour first (#237) — still needed, and kept separate. The user asked for data coverage here.
- A live hotel/places provider — out of scope. Inventory stays synthetic by design (AGENTS.md).

### Deviations

- Plan gap: free-form Haiku web research fabricated data. The Europe and Korea/Taiwan attempts returned 0 of 118 working image URLs, and one listing put the Reims cathedral in Paris; both outputs were discarded. Task 1.3 was added: a deterministic candidate fetcher (Wikidata SPARQL, Commons, the Wikipedia REST API, Wikivoyage) and `--online` verification (QID exists, coordinates within 1 km, image loads). Haiku now only selects and describes real candidates.
- Convention correction: the existing `visa.py` is generic ("many passports"), not specific to Vietnamese passport holders. New entries follow that convention and add one sentence for Vietnamese passport holders. Japan and South Korea are unchanged.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| summary shape | `python .claude/scripts/verify_summary.py --lane gh-237-city-coverage-expansion` | 0 | intake-time check | |

### Not auto-verified

- The accuracy of web-sourced hotel, place, visa and fx facts reached provenance only; tests check shape, not truth. Every source URL is recorded, and prices are marked as snapshot values.

### Rollback

- `git revert <sha>` — the change is additive. Hotels and places added by `seed_all` stay in existing DBs until a reseed.

### Harness-Delta

- none
