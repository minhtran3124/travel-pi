"""Task 1.1 — Store procedural namespace + instruction helpers (specs/agent-memory-layers)."""


def test_namespace_prefs_unchanged():
    """_prefs_namespace still returns ("users", user_id, "prefs")."""
    from app.memory.store import _prefs_namespace

    assert _prefs_namespace("u1") == ("users", "u1", "prefs")


def test_upsert_and_get_instructions():
    """Upsert two instructions, recall returns both; overwrite same key replaces."""
    from app.memory.store import get_instructions, get_store, upsert_instruction

    store = get_store("sqlite:///:memory:")
    upsert_instruction(store, "u1", "price_currency", {"text": "Always show EUR"})
    upsert_instruction(store, "u1", "greeting", {"text": "Address as Captain"})

    results = get_instructions(store, "u1")
    texts = {r["text"] for r in results}
    assert texts == {"Always show EUR", "Address as Captain"}


def test_instruction_overwrite_same_key():
    """Upserting the same key replaces the old value (not append)."""
    from app.memory.store import get_instructions, get_store, upsert_instruction

    store = get_store("sqlite:///:memory:")
    upsert_instruction(store, "u1", "style", {"text": "Be concise"})
    upsert_instruction(store, "u1", "style", {"text": "Be very detailed"})

    results = get_instructions(store, "u1")
    assert len(results) == 1
    assert results[0]["text"] == "Be very detailed"


def test_instructions_isolated_per_user():
    """Instructions for u1 don't leak into u2."""
    from app.memory.store import get_instructions, get_store, upsert_instruction

    store = get_store("sqlite:///:memory:")
    upsert_instruction(store, "u1", "rule", {"text": "u1 rule"})
    upsert_instruction(store, "u2", "rule", {"text": "u2 rule"})

    assert [r["text"] for r in get_instructions(store, "u1")] == ["u1 rule"]
    assert [r["text"] for r in get_instructions(store, "u2")] == ["u2 rule"]


def test_get_instructions_empty_user():
    """No instructions stored → empty list."""
    from app.memory.store import get_instructions, get_store

    store = get_store("sqlite:///:memory:")
    assert get_instructions(store, "u1") == []


def test_prefs_and_instructions_different_namespaces():
    """Preferences and instructions live in separate namespaces."""
    from app.memory.store import (
        get_instructions,
        get_store,
        search_preferences,
        upsert_instruction,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    upsert_instruction(store, "u1", "rule", {"text": "show EUR"})

    prefs = [p["text"] for p in search_preferences(store, "u1")]
    instrs = [i["text"] for i in get_instructions(store, "u1")]

    assert prefs == ["vegetarian"]
    assert instrs == ["show EUR"]
