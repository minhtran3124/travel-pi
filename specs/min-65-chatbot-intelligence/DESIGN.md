---
slug: min-65-chatbot-intelligence
doc: detail-design
created: 2026-07-12
status: proposed
depends_on: HLD.md (option decisions); already-shipped foundation — agent-memory-layers P1/P2, agent-memory-semantic, min-53, min-55, min-58
---

# Detail Design — MIN-65

File paths are relative to `apps/api/` unless noted otherwise.

## D1 — `trip_facts`: entity/slot state within a session

### Schema (`app/agents/state.py`)

```python
def merge_trip_facts(old: dict | None, new: dict | None) -> dict:
    """Reducer: a non-None new value overwrites; a known fact is never deleted."""
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if v is not None:
            merged[k] = v
    return merged

class TravelAgentState(MessagesState):
    ...
    trip_facts: Annotated[dict, merge_trip_facts]   # NEW
    preferences: str                                 # NEW (D2) — already-formatted text block
```

Normalized keys (all optional): `destination`, `origin`, `start_date` (ISO),
`end_date` (ISO), `adults`, `children`, `rooms`, `budget_amount`, `budget_currency`,
`cabin_class`, `hotel_area`. Thread-scoped (checkpointer-persisted within the
conversation); **not** written to BaseStore (per HLD §2 — per-turn slots don't belong in
the store).

### Injection (`system_with_summary`)

Fold in an additional block (after profile/instructions, before summary), only when
non-empty:

```
Known trip facts (already provided by the traveller — do NOT ask again;
if a required field is missing here, ask ONLY for that field):
- destination: Da Nang
- start_date: 2026-08-15 · end_date: 2026-08-20
- party: 2 adults, 1 child
```

Keeps current behavior: both call sites (`supervisor.py`, `subagents/_base.py`) go
through the same function — no call-site changes.

### Why this closes the summarizer-lossy gap

Facts live in a state field, independent of the summarizer LLM choosing to "remember to
keep" them. The summary only has to worry about conversational context anymore. No need
to touch the summarizer.

## D2 — Preference auto-injection for every sub-agent

`load_context_node` (`app/agents/nodes.py`) currently loads trip_context + instructions +
profile. Add: `search_preferences(store, user_id, limit=8)` (recency full-read, **not** a
semantic query — the store is small, per HLD §2), **excluding `PROFILE_KEYS`** (already
has its own profile block), formatted into a text block:

```
Traveller preferences (learned from past conversations — use to personalise,
confirm before acting on stale ones):
- diet: vegetarian
- hotel_type: prefers beachfront 4-5 star
```

→ `state["preferences"]` → folded into `system_with_summary`. Best-effort like the
profile block (store miss / no user → `""`). The journal tool `get_user_preferences`
stays as-is for deeper queries.

Token cost: ≤8 short lines per turn — acceptable (in line with the bounded full-read
principle).

## D3 — Supervisor: slot extraction + secondary intent (one LLM call)

### Schema (`app/agents/supervisor.py`)

```python
class ExtractedSlots(BaseModel):
    """Raw mentions — verbatim text, NOT self-resolved. Code will normalize it."""
    destination: str | None = None
    origin: str | None = None
    start_date_text: str | None = None   # e.g. "8/15", "next week"
    end_date_text: str | None = None     # e.g. "8/20", "5 days" (a duration also stays raw)
    adults: int | None = None
    children: int | None = None
    rooms: int | None = None
    budget_text: str | None = None       # e.g. "around 20 million", "$2000"
    cabin_class: str | None = None
    hotel_area: str | None = None

class SupervisorIntent(BaseModel):
    target_agent: Literal["planner","concierge","journal","booking","budget"]
    secondary_agent: Literal["planner","concierge","journal","budget"] | None = None
    language: str
    slots: ExtractedSlots | None = None
```

- `secondary_agent`: **excludes `booking`** (HLD non-goal) and the prompt requires it to
  differ from `target_agent`, set only when the user genuinely states 2 needs in one
  message. If `target_agent == "booking"` → code drops the secondary.
- Every slot field is optional → the model is never forced to make something up. Prompt:
  "extract ONLY what the traveller explicitly stated in this turn; leave null otherwise".

### Normalization in code (supervisor node, after the LLM call)

- `start_date_text`/`end_date_text` → `core.dates.resolve_travel_date(raw, today(ctx.timezone))`;
  resolve failure → **drop the slot** (never guess — consistent with the "never guess
  dates" rule from PR #84). A duration ("5 days") combined with a `start_date` → end =
  start + n-1; with no start date → drop.
- `budget_text` → parse a number + currency with a simple regex; on failure, keep the raw
  text in a `budget_note`? **No** — on failure, drop it (keep this simple for v1; the
  free text is still available in history).
- `adults/children/rooms` → int cast, drop if ≤0.
- `destination`/`origin` keep the raw text (fuzzy resolution already lives at the tool
  layer, `core/text.py`).

The current `Command(update={current_flow, language}, goto=...)` extends to:
`update={..., "trip_facts": normalized, "pending_flows": [secondary] if valid else []}`.

### Prompt `prompts/supervisor/v6.md` + `active.yaml: supervisor: 6`

Additions vs v5: (1) describe the slots + the rule "verbatim only, null when unsure";
(2) the secondary rule: "if the message contains two distinct requests (e.g. flight AND
hotel), set target to the one that unblocks first, secondary to the other; never
booking". **Mandatory note** (critical pattern `supervisor-active-yaml-is-a-pointer`):
create a new v6 file + flip the pointer, do not edit v5; the graph is baked at lifespan →
dev needs a rebuild (`docker exec api-api-1 touch app/main.py`).

### Routing-degradation risk & guardrails

A larger schema could reduce `target_agent` selection quality. Guardrails: (a) every new
field is optional; (b) MIN-58's eval `routing.json` dataset re-runs at the measurement
phase; (c) FakeLLM unit tests for both branches (with/without slots).

## D4 — Multi-intent dispatch: the `dispatch_next` node

### State

`pending_flows: list[str]` (defaults to `[]`, the supervisor writes at most one entry —
bounded to 2 intents/turn per HLD §3.3).

### Graph (`app/agents/graph.py`, node in `nodes.py`)

The current static edge `<sub-agent> → reflection` becomes `<sub-agent> → dispatch_next`:

```python
def dispatch_next(state) -> Command:
    pending = state.get("pending_flows") or []
    if pending:
        nxt, rest = pending[0], pending[1:]
        return Command(update={"current_flow": nxt, "pending_flows": rest}, goto=nxt)
    return Command(goto="reflection")
```

- No LLM call — a pure routing node.
- Reflection stays unchanged: it reviews the **final answer** (after both intents have
  run); the revise loop `goto=current_flow` → sub-agent → `dispatch_next` (queue already
  empty) → reflection: revise behavior is unchanged.
- The `plan` branch (HITL booking) does not go through dispatch — keeps its existing
  topology.
- The supervisor Command's `destinations=` doesn't need to change (still goes to 1
  sub-agent); `dispatch_next` is added to the graph's nodes.

The second sub-agent sees the first sub-agent's messages in state → it naturally
continues the thread ("the flight picked above") with no extra plumbing needed.

## D5 — Store hygiene (hardened extraction, kept minimal)

1. **Timestamps**: `upsert_preference/instruction/episode` (`app/memory/store.py`) also
   write `"updated_at": datetime.now(timezone.utc).isoformat()` into the value dict (no
   change to the index schema — `text` is still the embedded field). The D2 injection
   block can use this to prioritize recency once past the limit.
2. **Canonical keys against key-drift**: `prompts/memory_extraction/v5.md` (+ flip
   `active.yaml`) adds a canonical-key vocabulary: `diet, hotel_type, airline,
   cabin_class, budget_band, seat, travel_pace, language, ...` + the rule "reuse an
   existing canonical key when the fact updates a prior one; only invent a new key for a
   genuinely new fact" → a key-addressed upsert naturally becomes an UPDATE instead of a
   duplicate (a minimal form of Mem0's ADD/UPDATE — sufficient at this scale, per HLD
   §3.1).
3. **Not doing**: TTL/decay, an LLM contradiction pass, versioning — premature (HLD
   non-goals).

## D6 — Suggestion rule engine (`app/agents/suggestions.py`)

### API — stays compatible with both call sites

```python
def suggestions_for_flow(
    current_flow: str | None,
    *,
    trip_facts: dict | None = None,
    profile: dict | None = None,
    preferences: str = "",
) -> list[str]:   # still returns a list of i18n keys, MAX 3
```

- `routers/agent.py:306` (non-stream): has the final state → passes all parameters.
- `streaming/mapper.py:246` (done SSE): uses the same sink/final-state mechanism as
  `run_memory_extraction_from_stream` to obtain trip_facts/profile at drain time; if the
  point where the done event is built can't reach the final state → fall back to calling
  with `current_flow` alone as before (degrades to MIN-55 behavior, doesn't break
  anything). Exact details to be settled at implementation time (recorded in PLAN).

### Rule engine

An ordered rule table (specific → generic), taking the first matching keys until 3 are
filled; the final fallback = the current static `_FLOW_SUGGESTIONS` map (preserves the
"≥80% have a suggestion" AC — never fewer suggestions than today):

| Condition (example) | Suggested key |
|---|---|
| flow=booking & a flight was just booked & no hotel yet in trip_facts | `book_hotel_next` |
| flow=booking & a hotel was just booked | `transport_to_hotel`, `activities_near_destination` |
| trip_facts.start_date is within ≤14 days | `weather_before_trip`, `packing_tips` |
| profile.travel_group == family | `family_activities` |
| preferences contains a budget signal / flow=budget | `budget_check` |
| trip_facts.destination is present & flow=concierge | `local_tips_destination` |
| (fallback) | the static per-flow map, as in MIN-55 |

The ~8 new keys need a `Chat.followups.<key>.{label,prompt}` entry in
`apps/web/messages/en.json` + `vi.json` (the FE's `ChatSuggestions.tsx` resolves
dynamically — no component change needed). Interrupt-pending still suppresses
suggestions as before.

Deterministic → a plain unit test, no LLM required.

## D7 — Preference-aware re-rank inside the tools

### `app/tools/_ranking.py` (new)

```python
def rank_by_preference(items: list[T], preferences: str, extractors: ...) -> tuple[list[T], list[str]]
    """Stable sort: boost score = number of preference keywords matching the item's
    attributes. Returns (sorted items, matched_reasons) — reasons for the tool to fold
    into its summary string."""
```

- Deterministic keyword matcher (lowercase, with diacritic folding via `core/text.py`):
  hotel — star rating ("5 star"), area ("beach", "near the beach"), type; flight —
  airline name, time-of-day ("morning", "evening") mapped to departure hour. Preferences
  are free text → a keyword matcher is an accepted trade-off for v1 (limitation
  documented explicitly).
- **Stable sort** over the service's deterministic result → doesn't break the "same
  query = same result" rule (same user + same prefs → still deterministic).

### Wiring

`search_hotels`/`browse_hotels` (`tools/hotel_tools.py`), `search_flights`
(`tools/flight_tools.py`): receive `preferences: Annotated[str, InjectedState("preferences")]`
— **inline `Annotated`, NOT `args_schema=`** (documented gotcha:
`explicit-args-schema-breaks-langgraph-injection`). Re-rank before building the summary +
`panel_result`; when there's a match, append to the summary string:
`"Prioritized based on your preferences: <reasons>"` → serves both as ranking and as the
"reason attached" requirement (AC pillar 3). The panel keeps the re-ranked order.

## D8 — Prompt quality pass (one task, one voice)

| Prompt | New version | Added content |
|---|---|---|
| `communication_style` | v6 (active 5→6) | "Every recommendation carries a one-line reason tied to the traveller's stated facts or preferences ('since you're travelling with young kids…'). List answers end with the single most relevant next step." |
| `concierge` | v10 | Intent inference: proactively surface seasonal/weather/event implications ("July is peak season — worth booking early"); ask-only-missing checked against Known trip facts |
| `planner` | v8 | Ask-only-missing; default-with-confirm ("defaulting to 2 adults — can you confirm?") only for fields the tool signature doesn't require |
| `booking` | v7 | Ask-only-missing (tool args remain a hard gate — never relaxed) |

All of these: a new version file + flip `active.yaml` (never edit the old file); remember
the dev graph-rebuild step.

## D9 — Eval first, measure after (MIN-58 harness)

### Multi-turn harness (`eval/harness.py`)

`run_case` gains support for a new case shape (back-compat with a single `input`):

```jsonc
{
  "turns": ["Find a hotel in Da Nang 8/15-8/20, 2 adults 1 child", "What about flights?"],
  "new_thread_at": null,        // or an index — that turn opens a NEW thread_id, same user_id (cross-session)
  "metrics": ["memory_recall"]
}
```

- Same `thread_id` across turns (unless `new_thread_at` → a new thread, same user, same
  store — measures "prefs remembered across sessions"). `actual_output` = the final
  reply.
- Suggestions: the graph doesn't generate these itself → the harness calls
  `suggestions_for_flow(final_state...)` after the invoke and attaches it to the test
  case (retrieval-free, deterministic).

### Metrics (`eval/metrics_geval.py` + `run_deepeval.py`)

- `memory_recall` (GEval): "assistant reuses facts the traveller already provided (dates,
  party, destination, prefs) and does NOT re-ask for them; asking for a genuinely new
  field is fine."
- `suggestion_relevance`: 2 layers — deterministic (suggestions non-empty + key in the
  catalog; measures the ≥80% AC) + GEval relevance (does the key's EN label relate to the
  context).
- New datasets `eval/datasets/memory.json`, `suggestions.json`; registered in
  `loader.load_all()`; per-case rubric filter via `metadata`, as in the MIN-58
  calibration.

### Operations

The baseline runs **before** the implementation wave (P0), re-run at P4 → RESULTS.md
compares the delta. Note already recorded in project memory: eval bypasses DB config →
must run inside the container, needs a real judge key; no key → documented-skip, never a
silent pass.

## Test matrix (proof)

| Behavior | Check |
|---|---|
| reducer merge: new value overwrites, None does not delete | `tests/agents/test_trip_facts.py` |
| system_with_summary folds trip_facts/preferences; empty → base unchanged | same |
| supervisor: verbatim slots → normalized (date resolve, int cast, drop-on-fail) | `tests/agents/test_supervisor_slots.py` (FakeLLM) |
| supervisor: a valid secondary → pending_flows; booking as primary → secondary dropped | same |
| load_context: prefs → block (excluding PROFILE_KEYS); store miss → "" | `tests/agents/test_preferences_injection.py` |
| dispatch_next: pending → goto the next one in order; empty → reflection; revise loop doesn't break | `tests/agents/test_multi_intent_routing.py` |
| store: upsert writes updated_at; back-compat with old values missing the field | `tests/memory/test_store_timestamps.py` |
| extractor v5: canonical key reuse (FakeLLM) | extended `tests/memory/test_extractor.py` |
| suggestions: each rule + fallback + MAX 3 + key ∈ catalog | `tests/agents/test_suggestions_engine.py` |
| ranking: correct boost, stable sort, no-prefs → unchanged order, correct reasons | `tests/tools/test_preference_ranking.py` |
| tools: the `preferences` injection never leaks into the model schema | same |
| eval: multi-turn within one thread; new_thread_at splits the thread but keeps the same user | `tests/eval/test_harness_multiturn.py` (FakeLLM) |
| new prompts load through the registry + active.yaml points correctly | registry check in the verify task |

## Risks & mitigations

- **Routing degradation from a larger schema** → optional fields, routing eval re-run,
  FakeLLM tests (D3).
- **Slot normalization gets a date wrong** → reuse `core/dates` (already has its own test
  suite + the raise-don't-guess principle); on failure → drop.
- **Stale trip facts when the user changes plans** ("actually, let's go to Hue instead")
  → the new value overwrites via the reducer; old party size/dates could linger — the
  "Known trip facts" prompt includes "confirm if the traveller appears to have changed
  plans." Accepted as a residual risk for v1.
- **The streaming path can't obtain the final state for suggestions** → flow-only
  fallback (degrades to MIN-55 behavior, doesn't break the contract).
- **Keyword matcher ranks incorrectly** → boost-only (never filters out), stable sort
  preserves the original order within a tied score group.
- **`risk-corroboration` hook**: no new endpoint, no response-shape change; a prompt/test
  diff containing the word "session" or removing an assert could false-positive → handle
  per the recorded memory (`RISK_WARN_CATEGORIES` when needed).
