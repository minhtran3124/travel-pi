"""Memory tools degrade to an error string when the store/embeddings fail (#270)."""

from app.tools.memory_tools import (
    get_user_preferences,
    recall_past_trips,
    save_user_preference,
)


class _BrokenStore:
    """Store whose every call raises (e.g. a dead embedding key during search/put)."""

    def search(self, *a, **k):
        raise RuntimeError("429 insufficient_quota")

    def put(self, *a, **k):
        raise RuntimeError("429 insufficient_quota")


def test_memory_tools_return_error_text_instead_of_raising():
    store = _BrokenStore()
    saved = save_user_preference.invoke(
        {"key": "diet", "text": "vegetarian", "user_id": "u1", "store": store}
    )
    assert isinstance(saved, str) and "Could not" in saved
    got = get_user_preferences.invoke({"user_id": "u1", "query": "x", "store": store})
    assert isinstance(got, str) and "unavailable" in got
    recalled = recall_past_trips.invoke(
        {"query": "tokyo", "user_id": "u1", "store": store}
    )
    assert isinstance(recalled, str) and "unavailable" in recalled
