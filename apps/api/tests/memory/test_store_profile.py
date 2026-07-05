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
