# How each candidate file was fetched

Run from `apps/api/` (`python -m scripts.fetch_city_candidates …`). `--extra-*` adds named
items that Wikidata does not type with a usable P31 (or that the class filters miss); each
lands with `"strategy": "manual"` and still takes its label, coordinates and image from Wikidata.
Fetched 2026-09-26. A refetch can pick up Wikidata edits, so rebuild and re-run the source
checks afterwards (`python -m scripts.build_city_sources`, `check_seed_sources.py --online`).

| City | Command |
|---|---|
| Osaka | `Osaka Q35765 --max-km 15` |
| Kyoto | `Kyoto Q34600 --max-km 15` |
| Fukuoka | `Fukuoka Q26600 --max-km 15` |
| Sapporo | `Sapporo Q37951 --max-km 15` |
| Busan | `Busan Q16520 --max-km 20` |
| Jeju | `Jeju Q42142 --max-km 40 --extra-restaurant Q12593341` |
| Taipei | `Taipei Q1867 --max-km 15 --extra-place Q706761 --extra-place Q591131 --extra-place Q63227 --extra-restaurant Q697118` |
| Shanghai | `Shanghai Q8686 --max-km 25` |
| Beijing | `Beijing Q956 --max-km 25` |
| Guangzhou | `Guangzhou Q16572 --max-km 25` |
| Paris | `Paris Q90 --max-km 15 --extra-hotel Q111113654` |
| London | `London Q84 --max-km 20` |
| Lisbon | `Lisbon Q597 --max-km 15` |
| Rome | `Rome Q220 --max-km 15` |
| Sydney | `Sydney Q3130 --max-km 25` |
| Melbourne | `Melbourne Q3141 --max-km 25 --extra-hotel Q111407382` |
| Dubai | `Dubai Q612 --max-km 25` |
| Istanbul | `Istanbul Q406 --max-km 25 --extra-hotel Q111857299 --extra-hotel Q111857392` |
| New York | `"New York" Q60 --max-km 20` |
| Los Angeles | `"Los Angeles" Q65 --max-km 25 --extra-place Q575901` (Santa Monica Pier, Q595439, added by hand post-hoc via the same `_items_query`/image-resolution helpers `fetch_city_candidates.py` uses for `--extra-place`, to avoid a full city refetch changing other candidates -- replaces University of California, Los Angeles (Q174710) in selections, which SCHEMA.md excludes as a university) |
