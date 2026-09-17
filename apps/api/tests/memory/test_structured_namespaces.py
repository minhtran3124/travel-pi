"""Structured namespaces (research P2 row 2) — prefs / procedural / episodes.

Proves the three long-term memory kinds are isolated under their own
``("users", uid, <kind>)`` namespace for one user, and exercises the unified
typed-search abstraction (MemoryKind + search_memory + typed result dataclasses).
"""


def test_all_three_namespaces_mutually_isolated():
    """For one user, each kind's search returns ONLY its own kind — no leakage."""
    from app.memory.store import (
        get_instructions,
        get_store,
        search_episodes,
        search_preferences,
        upsert_episode,
        upsert_instruction,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    # Write one record of each kind for the SAME user, with distinct texts.
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    upsert_instruction(store, "u1", "price_display", {"text": "always show EUR"})
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {
            "text": "Da Nang slow beach trip",
            "trip_id": "trip_abc",
            "city": "Da Nang",
            "outcome": "approved",
        },
    )

    prefs = [p["text"] for p in search_preferences(store, "u1")]
    instrs = [i["text"] for i in get_instructions(store, "u1")]
    episodes = [e["text"] for e in search_episodes(store, "u1")]

    # Each kind returns exactly its own record...
    assert prefs == ["vegetarian"]
    assert instrs == ["always show EUR"]
    assert episodes == ["Da Nang slow beach trip"]
    # ...and none of the other kinds' texts leak in.
    assert "always show EUR" not in prefs and "Da Nang slow beach trip" not in prefs
    assert "vegetarian" not in instrs and "Da Nang slow beach trip" not in instrs
    assert "vegetarian" not in episodes and "always show EUR" not in episodes


def test_all_three_namespaces_isolated_per_user():
    """The three kinds are isolated per user too (u1 vs u2)."""
    from app.memory.store import (
        get_instructions,
        get_store,
        search_episodes,
        search_preferences,
        upsert_episode,
        upsert_instruction,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "u1 veg"})
    upsert_instruction(store, "u1", "price_display", {"text": "u1 EUR"})
    upsert_episode(
        store, "u1", "t1", {"text": "u1 trip", "city": "Rome", "outcome": "proposed"}
    )

    assert search_preferences(store, "u2") == []
    assert get_instructions(store, "u2") == []
    assert search_episodes(store, "u2") == []


# --- typed search abstraction ---


def test_memory_kind_enum_values():
    """MemoryKind maps to the three namespace kind strings."""
    from app.memory.store import MemoryKind

    assert MemoryKind.PREFERENCES.value == "prefs"
    assert MemoryKind.PROCEDURAL.value == "procedural"
    assert MemoryKind.EPISODES.value == "episodes"
    # Constructible from the raw strings (dispatchers rely on this).
    assert MemoryKind("prefs") is MemoryKind.PREFERENCES
    assert MemoryKind("episodes") is MemoryKind.EPISODES


def test_search_memory_dispatches_per_kind():
    """search_memory returns the right kind's values for each kind."""
    from app.memory.store import (
        get_store,
        search_memory,
        upsert_episode,
        upsert_instruction,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u", "diet", {"text": "veg"})
    upsert_instruction(store, "u", "price_display", {"text": "EUR"})
    upsert_episode(
        store, "u", "t1", {"text": "Da Nang", "city": "Da Nang", "outcome": "approved"}
    )

    assert [p["text"] for p in search_memory(store, "u", "prefs")] == ["veg"]
    assert [i["text"] for i in search_memory(store, "u", "procedural")] == ["EUR"]
    assert [e["text"] for e in search_memory(store, "u", "episodes")] == ["Da Nang"]


def test_search_memory_rejects_unknown_kind():
    """An unknown kind raises ValueError (typed validation)."""
    from app.memory.store import get_store, search_memory

    store = get_store("sqlite:///:memory:")
    try:
        search_memory(store, "u", "bogus")
        assert False, "expected ValueError for unknown kind"
    except ValueError:
        pass


def test_search_memory_typed_returns_typed_objects():
    """search_memory_typed returns Preference/Instruction/Episode dataclasses."""
    from app.memory.store import (
        Episode,
        Instruction,
        Preference,
        get_store,
        search_memory_typed,
        upsert_episode,
        upsert_instruction,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u", "diet", {"text": "veg"})
    upsert_instruction(store, "u", "price_display", {"text": "EUR"})
    upsert_episode(
        store,
        "u",
        "trip_abc",
        {
            "text": "Da Nang",
            "trip_id": "trip_abc",
            "city": "Da Nang",
            "outcome": "approved",
        },
    )

    prefs = search_memory_typed(store, "u", "prefs")
    instrs = search_memory_typed(store, "u", "procedural")
    episodes = search_memory_typed(store, "u", "episodes")

    assert isinstance(prefs[0], Preference)
    assert prefs[0].key == "diet" and prefs[0].text == "veg"
    assert isinstance(instrs[0], Instruction)
    assert instrs[0].key == "price_display" and instrs[0].text == "EUR"
    assert isinstance(episodes[0], Episode)
    assert episodes[0].key == "trip_abc"
    assert episodes[0].text == "Da Nang"
    assert episodes[0].trip_id == "trip_abc"
    assert episodes[0].city == "Da Nang"
    assert episodes[0].outcome == "approved"


def test_search_memory_default_limits_per_kind():
    """Only episodes keep a default recall limit; prefs/instructions return every row."""
    from app.memory.store import _EPISODE_DEFAULT_LIMIT

    assert _EPISODE_DEFAULT_LIMIT == 3
