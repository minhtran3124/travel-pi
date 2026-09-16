"""Stored-fact age reaches the system prompt (specs/agent-memory-layer-5 Task 2.1).

`state.py` has long told the model to "confirm before acting on stale ones" while
`nodes.py` rendered preferences as `- {key}: {text}` with no date — the model was asked to
judge staleness from information it never received. These tests pin the fix: each
preference and standing instruction carries a month-granularity recorded-age marker, the
marker is omitted (not guessed) when the stored row has no usable timestamp, and the
rendered age never contains a day count.

The day-count assertion is a cache guard, not a style guard: the preferences and
instructions blocks sit *before* `summary` in an implicitly cached system-prompt prefix
measured at 71.9%, so a string that changed daily would invalidate that prefix for every
user at each day rollover (docs/solutions/agent/prompt-caching-implicit-idle-eviction.md).
"""

from datetime import datetime, timedelta, timezone

from app.agents.nodes import load_context_node
from app.agents.state import system_with_summary
from app.memory.store import get_store, upsert_instruction, upsert_preference
from langchain_core.messages import SystemMessage

# Vocabulary that would betray a day-granularity age string.
_DAY_WORDS = ("today", "yesterday", "day", "days", "week", "weeks", "hour", "hours")


class _Runtime:
    """Minimal stand-in for the LangGraph runtime: only `.store` is read."""

    def __init__(self, store):
        self.store = store


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _load(store, user_id="u1"):
    return load_context_node({"user_id": user_id}, _Runtime(store))


def test_preferences_carry_a_recorded_age_marker():
    store = get_store()
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})

    result = _load(store)

    assert "diet: vegetarian" in result["preferences"]
    assert "(recorded in the last month)" in result["preferences"]


def test_standing_instructions_carry_a_recorded_age_marker():
    store = get_store()
    upsert_instruction(store, "u1", "no_redeye", {"text": "never book red-eye flights"})

    result = _load(store)

    assert "never book red-eye flights" in result["instructions"]
    assert "(recorded in the last month)" in result["instructions"]


def test_preferences_use_the_fine_vocabulary_and_instructions_the_coarse_one():
    """Granularity is chosen by prompt position, not by taste.

    `preferences` is the last block in `system_with_summary`, followed only by the
    daily date note `ground_current_date` appends, so finer phrasing there costs no
    cached prefix. `instructions` is position 3 — a change invalidates everything
    after it, `summary` included — so it keeps the coarse vocabulary.
    """
    store = get_store()
    store.put(
        ("users", "u1", "prefs"), "budget", {"text": "20m", "updated_at": _iso(200)}
    )
    store.put(
        ("users", "u1", "procedural"),
        "no_redeye",
        {"text": "no red-eyes", "updated_at": _iso(200)},
    )

    result = _load(store)

    assert "(recorded 4-8 months ago)" in result["preferences"]
    assert "(recorded 1-11 months ago)" in result["instructions"]


def test_older_rows_bucket_to_coarser_phrases():
    store = get_store()
    # Write through the store directly so updated_at can be backdated: upsert_preference
    # stamps "now", which is the whole point of _stamped().
    store.put(
        ("users", "u1", "prefs"), "budget", {"text": "20m VND", "updated_at": _iso(200)}
    )
    store.put(
        ("users", "u1", "prefs"), "airline", {"text": "VJ", "updated_at": _iso(800)}
    )

    prefs = _load(store)["preferences"]

    assert "budget: 20m VND (recorded 4-8 months ago)" in prefs
    assert "airline: VJ (recorded over a year ago)" in prefs


def test_missing_or_unparseable_timestamp_renders_no_marker():
    """Absent data renders as absent — never "unknown", never today's date."""
    store = get_store()
    store.put(("users", "u1", "prefs"), "pace", {"text": "slow"})  # no updated_at
    store.put(
        ("users", "u1", "procedural"),
        "greet",
        {"text": "call me Minh", "updated_at": "not-a-date"},
    )

    result = _load(store)

    assert result["preferences"] == "- pace: slow"
    assert result["instructions"] == "- call me Minh"
    assert "recorded" not in result["preferences"]
    assert "recorded" not in result["instructions"]


def test_rendered_age_never_uses_a_day_count():
    """Cache guard: no age string may change daily. Sweep a year of offsets."""
    for days in (0, 1, 2, 6, 13, 29, 30, 45, 200, 364, 366, 900):
        store = get_store()
        store.put(
            ("users", "u1", "prefs"), "k", {"text": "v", "updated_at": _iso(days)}
        )
        rendered = _load(store)["preferences"].lower()
        for word in _DAY_WORDS:
            assert word not in rendered, (
                f"day-count vocab {word!r} at {days} days: {rendered}"
            )


def test_age_marker_survives_into_the_assembled_system_prompt():
    """The marker must reach the real prompt, not just the state dict."""
    store = get_store()
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    state = {"user_id": "u1", **_load(store)}

    prompt = system_with_summary(state, SystemMessage(content="BASE"))

    assert isinstance(prompt, SystemMessage)
    assert "(recorded in the last month)" in prompt.content
    # Still one leading system message, and the base survives.
    assert prompt.content.startswith("BASE")


def test_prompt_names_the_marker_so_the_staleness_instruction_is_actionable():
    """state.py must tell the model the lines carry a recorded-at marker.

    Without this the existing "confirm before acting on stale ones" clause asks the
    model to judge staleness from information the prompt never explains.
    """
    store = get_store()
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    state = {"user_id": "u1", **_load(store)}

    content = system_with_summary(state, SystemMessage(content="BASE")).content

    assert "recorded" in content.lower()
    assert "confirm" in content.lower()
