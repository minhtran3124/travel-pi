# Diacritic-insensitive fuzzy matching — Intake Summary

Lane: normal
Confidence: high
Reason: Fold Vietnamese/Latin diacritics in the shared `_norm` of `app/core/text.py` so accented free-text ("Đà Nẵng") matches ASCII seed names ("Da Nang"). Changes existing matching behaviour across many callers (existing-behavior, multi-domain) but no hard gate fired — no security surface, no schema change, no external provider, no validation weakening, and core/text.py is not a harness high-blast file.
Flags: existing-behavior, multi-domain (shared util — 10+ services), weak-proof (mitigated: regression + new tests added)
Affects: app/core/text.py `_norm` → match_score / fuzzy_filter / best_match, used by cities, airports, places, hotels, tips, visa, currency, destination, routing services
Input-type: Change request (bug fix)
Route: in-place branch off v3 → implement + regression test + run affected suites (notify-and-proceed; high confidence, agreed approach "A")
Escalate: no

## Intent

User asked (across turns) why `get_local_tips` returned "không tìm thấy" for Đà Nẵng,
to verify the tool-calling flow, then to pick a fix approach. Verbatim scope-deciding lines:

> hãy kiểm tra kỹ lại xem flow gọi tool có đúng ko? có gọi dc tool ko? rôi tool có lấy dc data từ db ra ko

> suy nghĩ thử có cách fix nào nó common hơn, fix triệt để vs llm hay 1 cách nào đó tốt hơn, chuyên dụng hơn

> A

"A" = the agreed approach: fold diacritics in `core/text.py` `_norm` (deterministic,
shared, no LLM, no new dependency). Semantic-alias / geocoder resolver (option C) is
explicitly deferred.

## Diagnosis (evidence)

Tool flow is correct end-to-end (checkpoint shows a real `get_local_tips` tool_call with
`city="Đà Nẵng"`, gpt-4o-mini). Direct DB calls:
`{city:'Đà Nẵng'}→count=0`, `{city:'Da Nang'}→count=8`, `{country:'Vietnam'}→count=8`.
Root cause: `_norm` only `strip().lower()`; difflib ratio of "đà nẵng" vs "da nang" ≈ 0.57
< 0.6 threshold → no match. Seed cities are ASCII ("Da Nang").

## Rationale

- Fold at the matching layer (NFD + drop combining marks + explicit `đ`→`d`, which has no
  NFD decomposition) so the fix lands once and benefits all `best_match`/`fuzzy_filter`
  callers — the common, deterministic, root-level fix for the orthographic mismatch class.
- stdlib `unicodedata` only — preserves the file's "no external dependency" design.
- Rejected: LLM-side canonicalisation (non-deterministic; model can't know seed spelling;
  the bug arose precisely from delegating this to the model).

## Alternatives considered

- **Local fold inside `get_local_tips` only** — rejected: leaves every other name lookup
  broken for accented input.
- **Geocoder resolver (confident-seed-else-geocoder, like routing)** — deferred: handles
  semantic aliases + non-seed cities too, but is a heavier sync/async change; not needed
  for the diacritics class. If pursued, lift routing's pattern into a shared helper.
- **Alias seed table** — deferred: only covers semantic aliases; still needs folding.

## Status: implemented

Single-function change in `app/core/text.py` (`_norm` now folds diacritics) +
`import unicodedata`; new tests in `tests/unit/test_text.py`.

## Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| lint | `../../.venv/bin/ruff check app/core/text.py tests/unit/test_text.py` | 0 | ruff OK |
| text + geo + tip tool | `pytest tests/unit/test_text.py tests/api/geo tests/tools/test_tip_tools.py -q` | 0 | 86 passed |
| full API regression (all best_match callers) | `pytest tests/api -q` | 0 | 685 passed |
| live tip lookup (Postgres) | `get_local_tips.invoke({'city':'Đà Nẵng'})` | — | count=8 (was 0); Hà Nội→11, Huế→8 |

## Rollback

- Revert code: `git revert <sha>` (single-function change in `app/core/text.py`).
