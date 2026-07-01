"""Task 2.1 — Store episodes namespace + helpers (specs/agent-memory-layers P2)."""


def test_namespace_episodes():
    """_namespace(user_id, 'episodes') returns ('users', user_id, 'episodes')."""
    from app.memory.store import _namespace

    assert _namespace("u1", "episodes") == ("users", "u1", "episodes")


def test_upsert_and_search_episodes():
    """Upsert two episodes, semantic search returns both."""
    from app.memory.store import get_store, search_episodes, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {
            "text": "Da Nang beach trip, slow pace",
            "city": "Da Nang",
            "outcome": "approved",
        },
    )
    upsert_episode(
        store,
        "u1",
        "trip_xyz",
        {"text": "Tokyo city trip, fast pace", "city": "Tokyo", "outcome": "proposed"},
    )

    results = search_episodes(store, "u1")
    texts = {r["text"] for r in results}
    assert len(results) == 2
    assert "Da Nang beach trip, slow pace" in texts
    assert "Tokyo city trip, fast pace" in texts


def test_episode_overwrite_same_key():
    """Upserting the same key replaces the old value (not append)."""
    from app.memory.store import get_store, search_episodes, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {"text": "first version", "city": "Hanoi", "outcome": "proposed"},
    )
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {"text": "second version", "city": "Hanoi", "outcome": "approved"},
    )

    results = search_episodes(store, "u1")
    assert len(results) == 1
    assert results[0]["text"] == "second version"
    assert results[0]["outcome"] == "approved"


def test_episodes_isolated_per_user():
    """Episodes for u1 don't leak into u2."""
    from app.memory.store import get_store, search_episodes, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_a",
        {"text": "u1 trip", "city": "Rome", "outcome": "proposed"},
    )
    upsert_episode(
        store,
        "u2",
        "trip_a",
        {"text": "u2 trip", "city": "Paris", "outcome": "proposed"},
    )

    assert [r["text"] for r in search_episodes(store, "u1")] == ["u1 trip"]
    assert [r["text"] for r in search_episodes(store, "u2")] == ["u2 trip"]


def test_episodes_empty_user():
    """No episodes stored → empty list."""
    from app.memory.store import get_store, search_episodes

    store = get_store("sqlite:///:memory:")
    assert search_episodes(store, "u1") == []


def test_episodes_and_prefs_different_namespaces():
    """Episodes and preferences live in separate namespaces."""
    from app.memory.store import (
        get_store,
        search_episodes,
        search_preferences,
        upsert_episode,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    upsert_episode(
        store,
        "u1",
        "trip_a",
        {"text": "Da Nang trip", "city": "Da Nang", "outcome": "approved"},
    )

    prefs = [p["text"] for p in search_preferences(store, "u1")]
    episodes = [e["text"] for e in search_episodes(store, "u1")]

    assert prefs == ["vegetarian"]
    assert episodes == ["Da Nang trip"]


def test_episode_rich_metadata_round_trips():
    """Rich episode metadata (trip_id/city/outcome) round-trips through the store."""
    from app.memory.store import get_store, search_episodes, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_abc",
        {
            "text": "summary",
            "trip_id": "trip_abc",
            "city": "Da Nang",
            "outcome": "approved",
        },
    )

    results = search_episodes(store, "u1")
    assert len(results) == 1
    ep = results[0]
    assert ep["text"] == "summary"
    assert ep["trip_id"] == "trip_abc"
    assert ep["city"] == "Da Nang"
    assert ep["outcome"] == "approved"


def test_episodes_semantic_search_with_query():
    """A query ranks the semantically-closer episode first."""
    from app.memory.store import get_store, search_episodes, upsert_episode

    store = get_store("sqlite:///:memory:")
    upsert_episode(
        store,
        "u1",
        "trip_a",
        {"text": "beach holiday in Da Nang", "city": "Da Nang", "outcome": "approved"},
    )
    upsert_episode(
        store,
        "u1",
        "trip_b",
        {"text": "skiing in the Alps", "city": "Zermatt", "outcome": "proposed"},
    )

    results = search_episodes(store, "u1", query="beach trip")
    assert len(results) >= 1
    # The beach episode must rank at least as high as the ski one.
    assert results[0]["text"] == "beach holiday in Da Nang"
