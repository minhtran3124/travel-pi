from app.memory.store import get_profile, get_store, upsert_preference


def test_get_profile_returns_reserved_keys_in_order():
    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "gender", {"text": "female"})
    upsert_preference(store, "u1", "name", {"text": "Minh"})
    upsert_preference(
        store, "u1", "travel_group", {"text": "family with young children"}
    )
    # a non-reserved preference must NOT leak into the profile
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})

    result = get_profile(store, "u1")
    assert result == {
        "name": "Minh",
        "gender": "female",
        "travel_group": "family with young children",
    }
    # spec calls out PROFILE_KEYS order explicitly — dict == is order-insensitive,
    # so pin the key order directly.
    assert list(result.keys()) == ["name", "gender", "travel_group"]


def test_get_profile_omits_missing_and_blank():
    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u2", "name", {"text": "Lan"})
    upsert_preference(store, "u2", "gender", {"text": "   "})  # blank -> omit
    assert get_profile(store, "u2") == {"name": "Lan"}


def test_get_profile_empty_user():
    store = get_store("sqlite:///:memory:")
    assert get_profile(store, "u_none") == {}


def test_get_profile_skips_non_string_text_without_dropping_others():
    """A non-string text on one reserved key must not poison the others."""
    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u3", "name", {"text": "Minh"})
    upsert_preference(
        store, "u3", "travel_group", {"text": ["solo", "couple"]}
    )  # bad type
    # name survives; the malformed travel_group is skipped, not fatal
    assert get_profile(store, "u3") == {"name": "Minh"}
