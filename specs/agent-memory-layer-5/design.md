# Agent Memory — Layer 5 (P0 slice)

Status: approved (owner narrowed scope 2026-09-16)
Companion: `SUMMARY.md` (intake), `PLAN.md` (tasks)

## 1. Problem

`Agent Memory — The 5-Layer Playbook` (independently compiled, Sept 2026 — **not** an
Anthropic publication, and its 90% / +20% / −39% figures are Mem0 and Snowflake vendor
claims measured against a "stuff the whole history into every call" baseline this codebase
never had). Read as a checklist rather than a benchmark, it maps onto this project as:

| Layer | Here | Evidence |
| --- | --- | --- |
| 1 Working | present, one gap | `memory/summarizer.py`, `summarize_threshold=20`, `_safe_split()` keeps tool-call/tool-result pairs together |
| 2 Episodic | present, under-used | `store.upsert_episode` / `search_episodes` in ns `("users", uid, "episodes")`; recall only via the `recall_past_trips` tool, gated by `AgentContext.allow_episodic` |
| 3 Semantic | strongest layer | `prefs` ns + `PROFILE_KEYS` + pgvector index (`store._index_config`), auto-injected each turn at `agents/nodes.py:100-140` |
| 4 Procedural | present under a different meaning | ns `procedural` holds *the traveller's standing instructions*, not "a method that worked 3 times" |
| 5 Forgetting | **absent** | `grep -rni "ttl\|expire\|forget\|supersede\|prune\|retention\|archive" apps/api/app` → no hit under `app/memory/`. `_stamped()` writes `updated_at`; **no reader consumes it** |

Two consequences block a production launch.

**(a) The staleness instruction is a no-op.** `agents/state.py:191-194` tells the model
*"use to personalise, confirm before acting on stale ones"* — but `nodes.py:129-134` renders
each preference as `- {key}: {text}` with no date. The model is asked to judge staleness from
information it was never given. Today a budget captured eight months ago and one captured
this morning are byte-identical in the prompt.

**(b) There is no owner-facing route to the data.** `grep -rn "memor" apps/api/app/routers/*.py`
matches only the extraction-runner import in `agent.py`; `apps/web/src` has no memory surface.
The store holds inferred `gender` and `travel_group` (`store.PROFILE_KEYS`) written by a
background LLM extraction the traveller never sees. Beyond the privacy exposure, this is the
missing half of PR #214: a guard blocks *new* poison, but a poisoned standing instruction
already in `("users", uid, "procedural")` is re-injected into every future system prompt with
no way out short of hand-written SQL.

A third, smaller gap: `should_summarize()` counts messages (`len(messages) > 20`). A turn
that fans out `search_flights` + `search_hotels` can carry more tokens in eight messages than
a chatty turn carries in twenty.

## 2. Goals

- G1 — The model can distinguish a fresh fact from a stale one, without a scheduler.
- G2 — A traveller can see and permanently delete everything the agent stored about them,
  across all three kinds.
- G3 — History compression triggers on actual context pressure, not on a message count.
- G4 — No new dependency, no new table, no Alembic migration, no scheduler.

## 3. Non-goals

- Automatic expiry, supersession, or contradiction detection (P1 — §6).
- Anything from PR #214; that work stays in #214 (`SUMMARY.md` → Hard-gate narrowing).
- The deferred poisoning eval golden (#214's Task 4.1).
- Reading `agent_runs` / `agent_run_step` back as episodic memory (P1 — §6).

## 4. Design

### 4.1 P0#2 — Fact age in the prompt

`_stamped()` already writes an ISO-8601 `updated_at` on every store write. The data is
there; three things drop it before it reaches the model.

1. **`store.py` — carry the field through.** `Preference` / `Instruction` / `Episode`
   currently project only `key` + `text` in `from_item`. Add `updated_at: str | None = None`
   to all three and populate it. `search_memory_typed` then returns it for free;
   `search_memory` (dict variant) already returns the raw value, so it is unaffected.
2. **`store.py` — a `format_age(updated_at, *, now=None) -> str | None` helper.** Code
   computes, the model reads — per `docs/solutions/agent/llm-parses-code-computes.md`, an
   LLM handed two ISO dates and asked to subtract them is the failure mode, not the fix.
   Returns **`None`** when `updated_at` is missing or unparseable — never a guess, never a crash.
   English because the system prompt is assembled in English regardless of reply language
   (`state.py:with_reply_language` localises the *reply*, not the prompt).

   **The phrase is month-granularity, never a day count** — and the granularity below that is
   **chosen by the block's position in the prompt**. The block order in
   `state.py:system_with_summary` is
   `base → profile → account_email → instructions → trip_context → summary → trip_facts →
   preferences`, after which `ground_current_date` appends the daily date note outermost:

   - **`instructions` — position 3 — coarse** (`"in the last month"` / `"a few months ago"` /
     `"over a year ago"`). A string that changes here invalidates the cached prefix for
     everything after it, `summary` included. Caching is implicit, on, and measured at 80.3%
     (`docs/solutions/agent/prompt-caching-implicit-idle-eviction.md`).
   - **`preferences` — position 8, last — fine** (`"in the last month"` / `"2-3 months ago"` /
     `"about 6 months ago"` / `"about a year ago"` / `"over a year ago"`). It already sits after
     `summary`, and the only thing after it is a note that changes daily anyway, so the cached
     prefix stops just before that note regardless. Extra churn here costs one small block.

   > **Correction, 2026-09-16.** The first version of this section claimed *both* blocks sit
   > before `summary` and therefore applied one coarse vocabulary to both. That is false for
   > `preferences`, which is last. The correctness and intent reviews both caught it; the owner's
   > earlier approval had rested on the wrong premise and was re-put to them with the ordering
   > corrected. Never a day count is still right — the rest was not.

   The freshest phrase is `"in the last month"`, **not** `"this month"`: the code measures
   elapsed months, so a row stamped 20 Aug read on 16 Sep is 0 elapsed months but belongs to the
   previous calendar month. And a **future** timestamp returns `None` rather than the freshest
   label — an impossible stamp is unusable data, and unusable data renders as absent.
3. **`nodes.py` — render it.** Preferences become `- {key}: {text} (recorded {age})` and
   standing instructions `- {text} (recorded {age})`. When `format_age` returns `None`, the
   suffix is omitted entirely — a row with no timestamp renders exactly as it does today.

`state.py` then earns its existing sentence: reword the preferences block so it names the
marker (`"each line ends with when it was recorded; anything older than a few months should
be confirmed with the traveller before you act on it"`) instead of gesturing at a notion of
staleness the model cannot observe.

This is prompt text authored in Python, not a registry prompt under `app/prompts/<agent>/`,
so it does **not** need an `active.yaml` pointer bump
(`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md` does not apply here) — but it
does change every agent turn's system prompt, which is why the change is bounded to
appending a parenthetical and one clause.

**Why this substitutes for a forgetting engine at P0.** Expiry deletes on a fixed schedule
and is wrong whenever the guess is wrong. Showing the age moves the judgment to the point
where the context exists — the conversation — and costs one parenthetical per line.

### 4.2 P0#4 — Token-aware compression

`should_summarize(messages, threshold)` gains an **OR**, never a replacement:

```
too many messages  OR  estimated tokens > summarize_token_budget * 0.85
```

The existing message-count branch is untouched, so every current test stays valid and no
behavior is removed (which would trip the `remove-functionality` judgment gate).

Estimation is a deterministic character-count heuristic (`chars / 4`, tool-call arguments
included), not a provider tokenizer call. The decision happens *before* the model call, so a
real count would mean an extra round-trip on every turn; and the value is a ceiling, not
accounting.

`research-brief.md` upgrades this from a reasonable choice to **the only portable one**:
`langchain-core`'s base `get_num_tokens_from_messages` falls back to
`GPT2TokenizerFast.from_pretrained("gpt2")` via `transformers`, and **`transformers` is not
installed in this venv** — so the framework method raises for any model that does not override
it, including the test `FakeLLM`, i.e. the whole unit-test path. `ChatOpenAI` *does* override it
with tiktoken, but adopting that would make the compression trigger provider-coupled and
unverifiable offline, for a number that is a ceiling with 15% headroom. This reason belongs in a
code comment beside the estimator so nobody swaps it for the framework call later. `summarize_token_budget` lands in `core/config.py` next to `summarize_threshold`,
defaulting conservatively. `0.85` is the playbook's headroom factor and is the one number
worth borrowing from it — it leaves room for the system prompt and the next reply.

### 4.3 P0#3 — Memory management API + UI

**Store layer.** Two additions beside the existing helpers:

- `list_memory(store, user_id, kind, *, limit) -> list[dict]` — unfiltered listing with
  `key` and `updated_at` preserved (`search_memory` drops the key; the UI needs it as the
  delete handle).
- `delete_memory(store, user_id, kind, key) -> bool` — `store.delete(ns, key)`, idempotent.
  `kind` is coerced through `MemoryKind(kind)`, so an unknown kind raises before it can be
  interpolated into a namespace.

**API.** A new `app/routers/memory.py`:

| Route | Behavior |
| --- | --- |
| `GET /memory` | All three kinds for the caller, each row `{kind, key, text, updated_at, age}` |
| `DELETE /memory/{kind}/{key}` | Hard-delete one entry; 204 whether or not it existed |
| `DELETE /memory` | Delete everything for the caller; requires `?confirm=delete-all` |

The single load-bearing security property: **`user_id` comes from `CurrentUserDep` and from
nowhere else.** It is never read from a path segment, query parameter, or body. This mirrors
how `memory_tools.py` injects `user_id` via `InjectedState` specifically so the model cannot
address another traveller's namespace — the REST surface must not reopen what the tool layer
closed. The store is reached through `GraphDep` (`graph.store`), the same process-lifetime
instance the agent uses; building a second store per request is the connection leak
`lifespan.py:116-135` was written to fix.

`DELETE /memory` carries the confirmation token because it is the only irreversible action in
the spec and a bare `DELETE /memory` is one mis-wired fetch away from wiping a traveller's
history.

**Web.** A settings surface at `apps/web/src/app/settings/memory/` — `apps/web/src/app`
currently has no `settings` route, so this is a new page, not an edit. Three sections (one
per kind), each row showing the text, when it was recorded, and a delete control, plus a
guarded delete-all. Copy goes through the existing `messages/{en,vi}.json` i18n files; no
user-visible string is hardcoded. `schema.d.ts` is regenerated from OpenAPI rather than
hand-edited.

## 5. Risks

| Risk | Mitigation |
| --- | --- |
| Prompt text changes on every turn (§4.1) could shift agent behavior | Change is bounded to a parenthetical + one clause; `make eval-smoke` before the PR, and `make eval-check` against `eval/baselines/main.json` as the regression gate |
| ~~`PostgresStore.delete` may leave an orphaned pgvector embedding row~~ — **resolved** | `store_vectors` is created with `FOREIGN KEY (prefix, key) REFERENCES store(prefix, key) ON DELETE CASCADE` (`langgraph/store/postgres/base.py:104-112`, installed 1.2.6). The Postgres delete test stays, re-purposed as a **regression pin on the cascade** rather than an investigation. Precondition: it must exercise an *indexed* store, since the cascade ships in `VECTOR_MIGRATIONS` |
| **Prompt-cache regression from §4.1** — a silent *cost* regression no test catches | Bucketed age (§4.1) is the primary mitigation; measure with `cd apps/api && ../../.venv/bin/python -m scripts.cache_hit_report --since 24h` before and after, recorded in `PLAN.md` Task 4.1 |
| Hard delete is irreversible | Confirmation token on delete-all; per-entry delete is scoped to one key; recorded in `SUMMARY.md` → Rollback |
| The character-count token estimate is wrong for CJK / Vietnamese diacritics | It is a ceiling with 15% headroom, ORed with the existing count — an under-estimate degrades to today's behavior, it does not regress it |
| A third `status: active` PLAN would mis-bind the blast-radius and lane hooks | `PLAN.md` ships as `status: proposed`. `agent-memory-layer-5` sorts **before** both currently-active plans, so marking it active early would capture their gates — see the active-plan hook note |

## 6. Deferred — and what is refused outright

**P1, after launch:**

- **Per-kind TTL via LangGraph's built-in, not a hand-rolled read filter.** `research-brief.md`
  found the capability already installed: `TTLConfig(refresh_on_read, default_ttl,
  sweep_interval_minutes)`, per-item `ttl` on `put`, `expires_at` / `ttl_minutes` columns and a
  `sweep_ttl()` / `start_ttl_sweeper()` background thread (`langgraph/store/postgres/base.py`).
  The earlier sketch here — a read-time filter — would have re-implemented it *and* inherited the
  bug upstream already filed (langgraph#5178: a read filter and a sweeper disagreeing about what
  "expired" means). Two things make this a real design task rather than a config flip: the sweeper
  does **not** auto-start, and **`InMemoryStore` does not support TTL at all** — `BaseStore.put`
  *raises* `NotImplementedError` when handed a `ttl` (`store/base/__init__.py:912-916`), and this
  codebase degrades to `InMemoryStore` in tests and whenever pgvector is absent. Any adoption must
  branch on `store.supports_ttl`, never on the settings URL. Retention stays travel-calibrated,
  not playbook-calibrated: `prefs` never expire but re-confirm at ~180 days; `episodes` 365+ days
  (a seasonal trip memory is worth most exactly one year later); `procedural` never expire,
  managed through the UI this spec builds.
- Contradiction handling: on upsert to an existing key with materially different text, keep
  `previous` and flag rather than silently overwriting. The playbook routes conflicts to
  "human review"; here the reviewer is already in the loop and free — the traveller, mid-conversation.
- Read `agent_runs` / `agent_run_step` as an operator-facing episodic log (which flow fails,
  with which `error_type`). It is already the richest episodic record in the system and is
  currently used only for dashboard metrics. Value is in the operator query, not in the prompt.

**Refused, with reasons:**

| Playbook item | Why not |
| --- | --- |
| Knowledge graph / full ontology traversal | `nodes.py:129` does a bounded full read of 8 preferences. Multi-hop traversal answers a question this product does not ask. The useful fragment — validation rules — is PR #214's allowlist |
| Skill promotion + skill versioning (Layer 4 as the playbook means it) | Written for coding/DevOps agents with weekly-recurring tasks. A travel assistant has no "method that worked 3 times" to promote; the existing `procedural` namespace already fits the real need |
| Migrate to Mem0 / Zep | LangGraph Store + pgvector + typed `MemoryKind` is already in place. The playbook itself (§XI-D) says build custom first and migrate only for scale |
| Hierarchical summarization (daily → weekly → monthly) | Triggers at thousands of episodes. This store is at tens |
| Hot / warm / cold tiering | Cost optimisation for a scale not reached; adds a failure mode for no gain |
