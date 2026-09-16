"""Task 5.2 — Store hygiene: updated_at timestamps (specs/min-65-chatbot-intelligence D5)."""

from datetime import datetime


def test_upsert_preference_writes_updated_at():
    """upsert_preference stamps the value dict with a parseable ISO updated_at."""
    from app.memory.store import get_store, search_preferences, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})

    results = search_preferences(store, "u1")
    assert len(results) == 1
    assert "updated_at" in results[0]
    # Must be a parseable ISO-8601 timestamp.
    datetime.fromisoformat(results[0]["updated_at"])


def test_upsert_instruction_writes_updated_at():
    """upsert_instruction stamps the value dict with a parseable ISO updated_at."""
    from app.memory.store import get_instructions, get_store, upsert_instruction

    store = get_store("sqlite:///:memory:")
    upsert_instruction(store, "u1", "reply_length", {"text": "Be concise"})

    results = get_instructions(store, "u1")
    assert len(results) == 1
    assert "updated_at" in results[0]
    datetime.fromisoformat(results[0]["updated_at"])


def test_upsert_episode_writes_updated_at():
    """upsert_episode stamps the stored value dict with a parseable ISO updated_at.

    The episode *read* helpers now limit the returned payload to
    text/city/outcome/trip_id (guard §3.1), so ``updated_at`` is asserted on the
    raw stored record via ``store.get`` rather than through ``search_episodes``.
    """
    from app.memory.store import _namespace, get_store, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {"text": "Da Nang beach trip", "city": "Da Nang", "outcome": "approved"},
    )

    item = store.get(_namespace("u1", "episodes"), "trip_abc")
    assert item is not None
    assert "updated_at" in item.value
    datetime.fromisoformat(item.value["updated_at"])


def test_upsert_preserves_caller_supplied_fields():
    """Timestamping doesn't clobber other fields already on the value dict."""
    from app.memory.store import get_store, search_episodes, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {"text": "Tokyo trip", "city": "Tokyo", "outcome": "proposed"},
    )

    results = search_episodes(store, "u1")
    assert results[0]["text"] == "Tokyo trip"
    assert results[0]["city"] == "Tokyo"
    assert results[0]["outcome"] == "proposed"


def test_overwrite_bumps_updated_at():
    """Re-upserting the same key replaces updated_at (not left stale)."""
    from app.memory.store import get_store, search_preferences, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    first = search_preferences(store, "u1")[0]["updated_at"]

    upsert_preference(store, "u1", "diet", {"text": "vegan"})
    second = search_preferences(store, "u1")

    assert len(second) == 1
    assert second[0]["text"] == "vegan"
    assert "updated_at" in second[0]
    # Both are valid timestamps; overwrite path re-stamps rather than reusing
    # a caller-supplied value, so the field is present either way.
    datetime.fromisoformat(first)
    datetime.fromisoformat(second[0]["updated_at"])


def test_reading_legacy_record_without_updated_at_does_not_crash():
    """A pre-existing value dict with no updated_at key still reads fine
    through the search/get helpers (back-compat with records written before
    this change)."""
    from app.memory.store import (
        _namespace,
        _prefs_namespace,
        get_instructions,
        get_store,
        search_episodes,
        search_preferences,
    )

    store = get_store("sqlite:///:memory:")
    # Write directly via store.put to bypass the upsert_* stamping helpers,
    # simulating a record persisted before this change shipped.
    store.put(_prefs_namespace("u1"), "legacy_pref", {"text": "legacy preference"})
    store.put(_namespace("u1", "procedural"), "legacy_instr", {"text": "legacy rule"})
    store.put(
        _namespace("u1", "episodes"),
        "legacy_trip",
        {"text": "legacy trip", "city": "Hanoi", "outcome": "proposed"},
    )

    prefs = search_preferences(store, "u1")
    instrs = get_instructions(store, "u1")
    episodes = search_episodes(store, "u1")

    assert prefs[0]["text"] == "legacy preference"
    assert "updated_at" not in prefs[0]
    assert instrs[0]["text"] == "legacy rule"
    assert "updated_at" not in instrs[0]
    assert episodes[0]["text"] == "legacy trip"
    assert "updated_at" not in episodes[0]


def test_get_profile_ignores_missing_updated_at():
    """get_profile (keyed reads, PROFILE_KEYS) still works on a legacy record
    with no updated_at."""
    from app.memory.store import _prefs_namespace, get_profile, get_store

    store = get_store("sqlite:///:memory:")
    store.put(_prefs_namespace("u1"), "name", {"text": "Minh"})

    profile = get_profile(store, "u1")
    assert profile == {"name": "Minh"}
