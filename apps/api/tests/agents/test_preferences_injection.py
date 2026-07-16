"""Task 4.2 — preference auto-injection at load_context (MIN-65 DESIGN D2)."""

from types import SimpleNamespace

from langchain_core.messages import SystemMessage


def test_load_context_node_returns_non_profile_preferences_formatted():
    """Store has a mix of profile-key and non-profile-key prefs -> only the
    non-profile ones surface, formatted as "- {key}: {text}" lines."""
    from app.agents.nodes import load_context_node
    from app.memory.store import get_store, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u_pref", "diet", {"text": "vegetarian"})
    upsert_preference(
        store, "u_pref", "hotel_type", {"text": "prefers beachfront 4-5 star"}
    )
    # Profile-key entries must NOT leak into the preferences block (task 3.1/D2
    # already surfaces these via the dedicated `profile` block).
    upsert_preference(store, "u_pref", "name", {"text": "Minh"})
    upsert_preference(store, "u_pref", "travel_group", {"text": "solo"})

    state = {"messages": [], "user_id": "u_pref"}
    runtime = SimpleNamespace(store=store)
    result = load_context_node(state, runtime)

    assert "preferences" in result
    assert "- diet: vegetarian" in result["preferences"]
    assert "- hotel_type: prefers beachfront 4-5 star" in result["preferences"]
    assert "Minh" not in result["preferences"]
    assert "solo" not in result["preferences"]


def test_load_context_node_only_profile_keys_yields_empty_preferences():
    """Store has ONLY profile-key entries -> preferences resolves to ''."""
    from app.agents.nodes import load_context_node
    from app.memory.store import get_store, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u_only_profile", "name", {"text": "Minh"})

    state = {"messages": [], "user_id": "u_only_profile"}
    runtime = SimpleNamespace(store=store)
    result = load_context_node(state, runtime)

    assert result.get("preferences", "") == ""


def test_load_context_node_empty_store_yields_empty_preferences():
    """Store has no preferences at all -> preferences resolves to ''."""
    from app.agents.nodes import load_context_node
    from app.memory.store import get_store

    store = get_store("sqlite:///:memory:")

    state = {"messages": [], "user_id": "u_empty"}
    runtime = SimpleNamespace(store=store)
    result = load_context_node(state, runtime)

    assert result.get("preferences", "") == ""


def test_load_context_node_no_user_id_yields_empty_preferences():
    """No user_id in state -> no store lookup at all, no crash."""
    from app.agents.nodes import load_context_node
    from app.memory.store import get_store

    store = get_store("sqlite:///:memory:")

    state = {"messages": []}
    runtime = SimpleNamespace(store=store)
    result = load_context_node(state, runtime)

    assert result.get("preferences", "") == ""


def test_load_context_node_store_error_yields_empty_preferences():
    """search_memory_typed raising -> best-effort '', never propagates."""
    from app.agents.nodes import load_context_node

    class BoomStore:
        def search(self, *args, **kwargs):
            raise RuntimeError("store unavailable")

    state = {"messages": [], "user_id": "u_boom"}
    runtime = SimpleNamespace(store=BoomStore())
    result = load_context_node(state, runtime)

    assert result.get("preferences", "") == ""


def test_preferences_flow_from_load_context_into_system_with_summary():
    """Integration-style (light, per task 4.2 spec — the detailed rendering test
    already lives in test_trip_facts.py from task 3.1): prove load_context_node's
    output actually flows through system_with_summary, without routing through
    the full graph/supervisor (avoids coupling to task 4.1's in-flight work on
    supervisor.py, running in parallel on this same branch)."""
    from app.agents.nodes import load_context_node
    from app.agents.state import system_with_summary
    from app.memory.store import get_store, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u_flow", "diet", {"text": "vegetarian"})

    state = {"messages": [], "user_id": "u_flow"}
    runtime = SimpleNamespace(store=store)
    result = load_context_node(state, runtime)

    combined = system_with_summary({**state, **result}, SystemMessage(content="BASE"))
    assert "Traveller preferences" in combined.content
    assert "- diet: vegetarian" in combined.content
