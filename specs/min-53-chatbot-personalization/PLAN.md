---
slug: min-53-chatbot-personalization
status: shipped
owner: Minh Tran
created: 2026-07-05
---

# Chatbot Personalization (name / gender / travel-group) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Let the travel agent proactively (but softly, optionally) learn the traveller's name, gender, and who they're travelling with, persist those in the existing memory store, and inject them into every turn's system prompt so suggestions and address are personalized.

**Architecture:** Reuse the existing per-user LangGraph memory store `preferences` namespace — no schema, no migration. Three reserved preference keys (`name`, `gender`, `travel_group`) are (a) *asked for* by soft-prompt guidance added to the suggestion-emitting sub-agents (concierge, planner) at suggestion-time, (b) *captured* by the existing background `memory_extraction` LLM (prompt nudged to emit those keys — the extractor already parses free-form `{key,text}` preferences with no code change), and (c) *injected* into the leading system message via a new `TravelAgentState.profile` field loaded in `load_context_node`, mirroring exactly how procedural `instructions` already flow (`specs/agent-memory-layers`).

**Tech Stack:** Python 3.10+, LangGraph (`StateGraph`, `BaseStore`), Pydantic v2, file-backed prompt registry (`app/prompts/<name>/vN.md` + `active.yaml`), pytest + `FakeLLM`.

---

## 1. Motivation

MIN-53: personalize the agentic chatbot so it communicates naturally (address the traveller by name, adjust tone) and gives better suggestions (family-with-kids → kid-friendly hotels; couple → romantic rooms; solo/friends → hostels/social spaces). Do it via gentle, optional, skippable questions — never a blocking form.

## 2. Non-goals

- **No DB schema / migration.** Personalization rides the existing `preferences` store namespace. If a structured DB profile is ever wanted, that is a separate high-risk ticket (would re-trigger the data-model gate).
- **No new API endpoint or response-envelope change.** Behavior is conversational only; `/agent/*` contract is unchanged.
- **No mandatory collection.** Gender is sensitive/PII — the agent asks at most once, lightly, and must proceed unblocked if the traveller skips or declines. No validation coercion, no enum forcing on the user.
- **No deterministic test of the LLM's *asking* behavior.** Prompt-driven asking is verified by prompt review + phase-level manual UAT; the automated tests cover the capture→store→inject *code* path.
- **No change to booking/budget/journal/supervisor prompts.** Only the two suggestion agents ask.

## 3. Success Criteria

1. A seeded `name`/`gender`/`travel_group` preference appears as a "Traveller profile" block in the sub-agent system prompt on the next turn (automated: injection test).
2. `TravelAgentState.profile` folds into the single leading `SystemMessage` before `instructions`, and an empty profile leaves the prompt byte-identical to today (automated: state tests).
3. `get_profile()` returns only the reserved keys that exist with non-empty text (automated: store test).
4. `active.yaml` resolves the new `memory_extraction` / `concierge` / `planner` versions and every active prompt still loads (automated: registry smoke test).
5. Full suite green: `make test`. Lint clean: `ruff check app scripts`. **Implementer note:** the store's semantic index embeds `text` on `upsert_preference`; an `apps/api/.env` with `OPENAI_API_KEY=test` breaks embedding on put and will fail the new store/injection tests — run the suite with `.env` moved aside (same as existing memory tests).
6. Manual UAT (phase-level, non-blocking): in a live-ish `FakeLLM`-free chat, the agent asks the group question once before hotel suggestions, accepts a skip gracefully, and addresses the traveller by name on a later turn once the profile is stored.

## 4. Tasks

Reserved preference keys (single source of truth for this feature): **`name`**, **`gender`**, **`travel_group`**. Value shape is the existing `{"text": "..."}` preference payload; `text` holds a concise value (e.g. `"Minh"`, `"female"`, `"family with young children"`).

### Task 1.1 — Profile read helper in the store (wave 1)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/memory/store.py, apps/api/tests/memory/test_store_profile.py</files>
  <action>Add PROFILE_KEYS = ("name", "gender", "travel_group") and get_profile(store, user_id) -> dict[str, str] to store.py, near search_preferences. It reads each reserved key with store.get(_prefs_namespace(user_id), key), and includes it in the returned dict only when the item exists AND item.value.get("text","").strip() is non-empty. Order the returned dict in PROFILE_KEYS order. Do NOT use search_preferences (semantic ranking would drop/reorder keys); use direct keyed get so the three fields are exact and stable.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_store_profile.py -x</verify>
  <done>get_profile returns exactly the seeded reserved keys with non-empty text, in PROFILE_KEYS order; unknown/empty keys omitted; empty-store user returns {}.</done>
</task>
```

TDD steps:

- [ ] **Step 1 — failing test** `tests/memory/test_store_profile.py`:

```python
from app.memory.store import get_store, get_profile, upsert_preference


def test_get_profile_returns_reserved_keys_in_order():
    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "gender", {"text": "female"})
    upsert_preference(store, "u1", "name", {"text": "Minh"})
    upsert_preference(store, "u1", "travel_group", {"text": "family with young children"})
    # a non-reserved preference must NOT leak into the profile
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})

    assert get_profile(store, "u1") == {
        "name": "Minh",
        "gender": "female",
        "travel_group": "family with young children",
    }


def test_get_profile_omits_missing_and_blank():
    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u2", "name", {"text": "Lan"})
    upsert_preference(store, "u2", "gender", {"text": "   "})  # blank -> omit
    assert get_profile(store, "u2") == {"name": "Lan"}


def test_get_profile_empty_user():
    store = get_store("sqlite:///:memory:")
    assert get_profile(store, "u_none") == {}
```

- [ ] **Step 2 — run, expect fail** `cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_store_profile.py -x` → ImportError: cannot import name `get_profile`.
- [ ] **Step 3 — implement** in `app/memory/store.py` (after `search_preferences`, ~line 136):

```python
# Reserved preference keys for MIN-53 personalization. These three ride the
# existing prefs namespace (no schema) and are auto-injected each turn.
PROFILE_KEYS: tuple[str, ...] = ("name", "gender", "travel_group")


def get_profile(store: BaseStore, user_id: str) -> dict[str, str]:
    """Return the traveller's personalization profile: reserved preference keys
    (:data:`PROFILE_KEYS`) that exist with non-empty text, in reserved-key order.

    Uses direct keyed ``store.get`` rather than semantic ``search_preferences`` so
    the three fields are exact and never reordered/dropped by similarity ranking.

    :param store: Long-term store to read from.
    :param user_id: Owning user's id.
    :return: ``{key: text}`` for each reserved key present with non-blank text.
    """
    profile: dict[str, str] = {}
    for key in PROFILE_KEYS:
        item = store.get(_prefs_namespace(user_id), key)
        if item is not None:
            text = item.value.get("text", "").strip()
            if text:
                profile[key] = text
    return profile
```

- [ ] **Step 4 — run, expect pass** same pytest command → 3 passed.

### Task 1.2 — `profile` state field + system-prompt fold (wave 1)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/agents/state.py, apps/api/tests/agents/test_state_system_prompt.py</files>
  <action>Add `profile: str` to TravelAgentState (a compact "who the traveller is / how to address them" block). In system_with_summary, fold it in as a "Traveller profile:" section placed FIRST after base (before instructions) so name/gender carry the most weight for address/tone. Update the early-return guard so an all-empty (profile+instructions+trip_context+summary) state still returns base unchanged. Do not touch any other field's ordering.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_system_prompt.py -x</verify>
  <done>profile in TravelAgentState.__annotations__; folded under "Traveller profile:" before "Standing traveller instructions"; empty profile alone returns base unchanged.</done>
</task>
```

TDD steps:

- [ ] **Step 1 — failing tests** append to `tests/agents/test_state_system_prompt.py`:

```python
def test_profile_field_in_state_schema():
    from app.agents.state import TravelAgentState
    assert "profile" in TravelAgentState.__annotations__


def test_system_with_summary_folds_profile():
    from app.agents.state import system_with_summary
    base = SystemMessage(content="BASE")
    combined = system_with_summary({"profile": "- Name: Minh"}, base)
    assert "Traveller profile:" in combined.content
    assert "- Name: Minh" in combined.content
    assert "BASE" in combined.content


def test_system_with_summary_profile_before_instructions():
    from app.agents.state import system_with_summary
    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"profile": "- Name: Minh", "instructions": "Always show EUR"}, base
    )
    c = combined.content
    assert c.index("Traveller profile:") < c.index("Standing traveller instructions")


def test_system_with_summary_empty_profile_unchanged():
    from app.agents.state import system_with_summary
    base = SystemMessage(content="BASE")
    assert system_with_summary({"profile": ""}, base) is base
```

- [ ] **Step 2 — run, expect fail** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_system_prompt.py -x` → KeyError/assert on missing `profile`.
- [ ] **Step 3 — implement** in `app/agents/state.py`:
  - Add to `TravelAgentState` (after `instructions`, before `plan_approved`):

```python
    profile: str  # personalization block (name/gender/travel-group); injected at model call
```

  - In `system_with_summary`, update the guard + fold (profile first, before instructions):

```python
    trip_context = state.get("trip_context")
    summary = state.get("summary")
    instructions = state.get("instructions")
    profile = state.get("profile")
    if not trip_context and not summary and not instructions and not profile:
        return base
    parts = [base.content]
    if profile:
        parts.append(f"Traveller profile:\n{profile}")
    if instructions:
        parts.append(f"Standing traveller instructions:\n{instructions}")
    if trip_context:
        parts.append(f"Current trip context:\n{trip_context}")
    if summary:
        parts.append(f"Summary of earlier conversation:\n{summary}")
    return SystemMessage(content="\n\n".join(parts))
```

  - Update the docstring's summary line to mention `profile` is folded first.

- [ ] **Step 4 — run, expect pass** same pytest command → all green (existing instruction tests still pass — ordering unchanged for them).

### Task 2.1 — Inject profile in `load_context_node` (wave 2)

Depends on 1.1 (`get_profile`) and 1.2 (`profile` field). Mirrors the existing instruction-load block.

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/nodes.py, apps/api/tests/agents/test_profile_injection.py</files>
  <action>In load_context_node, after the procedural-instructions block, add a best-effort profile load: call get_profile(store, user_id); if non-empty, set result["profile"] to a bullet block using human labels {name:"Name", gender:"Gender", travel_group:"Travelling as"} in PROFILE_KEYS order. Wrap in try/except logging like the instruction block (never fail the turn on a store error). Add the get_profile import to the existing `from app.memory.store import ...` line.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_profile_injection.py -x</verify>
  <done>A seeded profile reaches the concierge system prompt as a "Traveller profile:" block with the values; an empty-profile user's prompt has no such block.</done>
</task>
```

TDD steps:

- [ ] **Step 1 — failing test** `tests/agents/test_profile_injection.py` (mirror `test_procedural_injection.py`):

```python
"""MIN-53 — personalization profile injection into the sub-agent system prompt."""

from langchain_core.messages import HumanMessage, SystemMessage


def _capturing_graph(store):
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver

    captured: dict = {}

    class CapturingFakeLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    main = CapturingFakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Here are some options"] * 4,
    )
    fast = FakeLLM(responses=["OK"])
    graph = build_graph(llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store)
    return graph, captured


def _system_content(captured):
    system_msgs = [m for m in captured["messages"] if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 1, "expected exactly one leading SystemMessage"
    return system_msgs[0].content


def test_profile_reaches_system_prompt():
    from app.memory.store import get_store, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u_prof", "name", {"text": "Minh"})
    upsert_preference(store, "u_prof", "travel_group", {"text": "family with young children"})

    graph, captured = _capturing_graph(store)
    graph.invoke(
        {"messages": [HumanMessage(content="hotels in Da Nang?")], "user_id": "u_prof"},
        {"configurable": {"thread_id": "t_prof"}},
    )
    content = _system_content(captured)
    assert "Traveller profile:" in content
    assert "Minh" in content
    assert "family with young children" in content


def test_no_profile_block_for_empty_user():
    from langgraph.store.memory import InMemoryStore

    graph, captured = _capturing_graph(InMemoryStore())
    graph.invoke(
        {"messages": [HumanMessage(content="hi")], "user_id": "u_empty_prof"},
        {"configurable": {"thread_id": "t_empty_prof"}},
    )
    assert "Traveller profile:" not in _system_content(captured)
```

- [ ] **Step 2 — run, expect fail** → assertion fail ("Traveller profile:" absent) because `load_context_node` doesn't load the profile yet.
- [ ] **Step 3 — implement** in `app/agents/nodes.py`:
  - Change the import (line 29): `from app.memory.store import get_instructions, get_profile`
  - After the instruction block (after line 82, still inside `if user_id and store is not None:`), add:

```python
        try:
            profile = get_profile(store, user_id)
            if profile:
                labels = {"name": "Name", "gender": "Gender", "travel_group": "Travelling as"}
                result["profile"] = "\n".join(
                    f"- {labels[k]}: {v}" for k, v in profile.items()
                )
                logger.info("[agent] node=load_context profile=%d", len(profile))
        except Exception:
            logger.exception("[agent] load_context: profile load failed")
```

- [ ] **Step 4 — run, expect pass** same pytest command → 2 passed.
- [ ] **Step 5 — no-regression** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_procedural_injection.py -x` → still green.

### Task 3.1 — Prompts: ask softly (concierge/planner) + capture (extraction) (wave 3)

Prompt-only + config. No deterministic behavior test (asking is LLM-driven); verify = every active prompt still loads + lint. New version files (never edit shipped versions — registry pattern).

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/prompts/memory_extraction/v3.md, apps/api/app/prompts/concierge/v8.md, apps/api/app/prompts/planner/v5.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/prompts/test_active_versions_load.py</files>
  <action>Create memory_extraction/v3.md (copy v2 + add a reserved-key personalization capture rule), concierge/v8.md (copy v7 + add a "Personalize before suggesting" soft-ask section), planner/v5.md (copy v4 + same soft-ask, harmonized with the existing hotel-detail guardrail). Bump active.yaml: memory_extraction 3, concierge 8, planner 5. Prepend a CHANGELOG entry. Add a smoke test asserting registry.get resolves every name in active.yaml to non-empty text.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_active_versions_load.py tests/prompts/test_registry.py tests/prompts/test_concierge_prompt.py -x && ruff check app/prompts</verify>
  <done>active.yaml points to the 3 new versions; all active prompts load non-empty; existing prompt tests still pass.</done>
</task>
```

Prompt content:

- [ ] **Step 1 — `memory_extraction/v3.md`** — copy v2.md verbatim, then add this bullet to the `Rules:` list (after the `preferences` bullet):

```markdown
- **personalization (reserved keys)** — when the traveller volunteers who they
  are or who they travel with, capture it as a `preferences` entry using one of
  these exact reserved keys, with a **concise** `text` value:
  - `name` — how they want to be addressed, e.g. `"Minh"`.
  - `gender` — only if they state it; store their own words, e.g. `"female"`.
  - `travel_group` — trip company/type, e.g. `"solo"`, `"couple"`,
    `"family with young children"`, `"group of friends"`, or a party size like
    `"4 adults"`.
  Capture these only when the traveller actually states them — never infer or
  guess gender/name/group from context.
```

- [ ] **Step 2 — `concierge/v8.md`** — copy v7.md, add this section right before `## Hotels`:

```markdown
## Personalize before suggesting

Better suggestions come from knowing who's travelling. If you're about to give
destination, activity, or hotel recommendations and you don't yet know the
traveller's trip company, ask **one** light, optional question first — e.g.
"Bạn đi một mình hay cùng ai để mình gợi ý hợp hơn?" / "Are you travelling solo,
as a couple, with family, or friends?". Keep it a single soft nudge:

- Ask at most once. If they skip, don't know, or decline, proceed normally with a
  sensible general suggestion — **never block** the recommendation on an answer.
- Never demand name or gender, and never ask for gender directly; only use those
  if they're already in the traveller profile (addressing them by name, matching
  tone). Treat them as nice-to-have, not required.
- Use what you know: family-with-kids → kid-friendly options; couple → romantic/
  quieter picks; solo/friends → social/hostel-style or lively areas.
```

- [ ] **Step 3 — `planner/v5.md`** — copy v4.md, add the same "Personalize before suggesting" section after `## How to Work` (before `## Guardrails`), worded for itinerary planning. Keep the existing hotel-detail guardrail intact; the soft-ask is about *trip company/vibe*, distinct from the *required* check-in/rooms/guests the booking guardrail already collects — note that distinction in one line so the two don't read as contradictory.

- [ ] **Step 4 — `active.yaml`** — set:

```yaml
concierge: 8
planner: 5
memory_extraction: 3
```

- [ ] **Step 5 — `CHANGELOG.md`** — prepend:

```markdown
## v-min-53 — proactive personalization (name / gender / travel-group)

MIN-53: agent softly, optionally learns who the traveller is and who they travel
with, to personalize address and suggestions. Stored in the existing prefs store
under reserved keys (`name`, `gender`, `travel_group`) — no schema. Injected each
turn via `TravelAgentState.profile` (`app/agents/nodes.py` load_context_node).

- **memory_extraction v3** — capture the three reserved personalization keys when
  the traveller volunteers them; never infer gender/name/group.
- **concierge v8 / planner v5** — added "Personalize before suggesting": one light,
  optional, skippable question about trip company before giving recommendations;
  never block on it; never ask for gender directly.

`active.yaml`: concierge → 8, planner → 5, memory_extraction → 3. Others unchanged.
```

- [ ] **Step 6 — smoke test** `tests/prompts/test_active_versions_load.py`:

```python
def test_every_active_version_loads_nonempty():
    import yaml
    from pathlib import Path
    from app.prompts.registry import registry

    active = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "app/prompts/active.yaml").read_text()
    )
    for name in active:
        text = registry.get(name)
        assert text and text.strip(), f"active prompt {name} loaded empty"


def test_min53_bumped_versions_active():
    """Guard against an active.yaml typo — the three bumped names resolve to the new versions."""
    import yaml
    from pathlib import Path

    active = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "app/prompts/active.yaml").read_text()
    )
    assert active["concierge"] == 8
    assert active["planner"] == 5
    assert active["memory_extraction"] == 3
```

(Adjust the `parents[..]` depth / loader to match `test_registry.py`'s existing pattern if it already exposes a helper — reuse over reinvent.)

- [ ] **Step 7 — run verify** the task `<verify>` command → all pass, lint clean.

## 5. Risks

- **PII / privacy (gender).** Mitigated by prompt rules: ask at most once, never demand, never ask gender directly, never infer, always skippable. No new persistence surface beyond the existing prefs store. If review wants gender dropped entirely, remove it from `PROFILE_KEYS` + the extraction bullet + labels — isolated change.
- **Prompt bloat / cross-agent leakage.** Only concierge + planner get the soft-ask (not booking/budget/journal/supervisor). The profile *injection* is universal (address/tone) but tiny and gated on non-empty profile — empty profile = byte-identical prompt (guarded + tested).
- **Semantic-search reorder.** Avoided by using keyed `store.get` in `get_profile`, not `search_preferences`.
- **Contradiction with the hotel-detail guardrail (planner).** The soft-ask is about trip *company/vibe*; the guardrail is about *required booking details*. Step 3 adds a one-line note distinguishing them.
- **Non-deterministic asking.** Cannot unit-test the LLM asking at the right time; covered by prompt review + phase-level manual UAT (Success Criterion 6). Ties into MIN-58 (eval harness) for future automated coverage.
- **Lane re-trigger.** If implementation drifts toward a structured DB profile (new table/column), stop — that trips the data-model hard gate → escalate to high-risk per in-flight checks.

## 6. Status Log

- 2026-07-05 — Plan drafted (proposed). Intake: `SUMMARY.md` (lane normal, confidence high). Branch `feat/min-53-chatbot-personalization` off `v3`.
- 2026-07-05 — Wave 1 complete (status active). Task 1.1 `ace1c75` (+ review hardening `7fbf53c`), Task 1.2 `18b2964`. Both two-stage reviewed ✅.
- 2026-07-05 — Wave 2 complete. Task 2.1 `bf7c452` (profile injection in load_context_node). Two-stage reviewed ✅ (5/5 tests incl. no-regression).
- 2026-07-05 — Wave 3 complete. Task 3.1 `651d984` (prompts: ask + capture; active.yaml; CHANGELOG; smoke test). Two-stage reviewed ✅ (9/9).
- 2026-07-05 — Ship gates. Correctness review → 1 Medium bug (get_profile non-string text) fixed `dc58563`. Intent review → 2 findings escalated + resolved with requester: name-ask added `c00eaa6`, gender narrowing confirmed (see ESCALATIONS.md). Blast-radius suite 168 passed; full suite blocked only by dev Postgres down (env, not regression).
- 2026-07-05 — shipped via `feat/min-53-chatbot-personalization` (PR #68)

## 7. Wave Map

| Wave | Tasks | Parallelism | Files disjoint? |
|------|-------|-------------|-----------------|
| 1 | 1.1 store helper, 1.2 state field+fold | 2 parallel | ✅ `store.py`+test vs `state.py`+test |
| 2 | 2.1 load_context injection | single | depends on 1.1+1.2 |
| 3 | 3.1 prompts + active.yaml + changelog | single | independent of code; last so injection path exists first |
