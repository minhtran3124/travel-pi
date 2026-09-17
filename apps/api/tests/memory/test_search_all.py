"""Instruction and preference reads return every stored row, however many pages it takes."""

from app.memory.store import (
    MemoryKind,
    get_instructions,
    get_store,
    search_memory_typed,
    search_preferences,
)


def _seed(store, namespace, count):
    texts = [f"note {i}" for i in range(count)]
    for i, text in enumerate(texts):
        store.put(namespace, f"k{i:03d}", {"text": text})
    return texts


def test_get_instructions_returns_every_row_across_pages():
    store = get_store("sqlite:///:memory:")
    expected = _seed(store, ("users", "u_pages", "procedural"), 250)

    result = get_instructions(store, "u_pages")

    assert [row["text"] for row in result] == expected


def test_search_preferences_returns_every_row_across_pages():
    store = get_store("sqlite:///:memory:")
    expected = _seed(store, ("users", "u_pages", "prefs"), 120)

    result = search_preferences(store, "u_pages")

    assert [row["text"] for row in result] == expected


def test_typed_search_is_unbounded_except_for_episodes():
    store = get_store("sqlite:///:memory:")
    _seed(store, ("users", "u_typed", "prefs"), 12)
    _seed(store, ("users", "u_typed", "episodes"), 5)

    assert len(search_memory_typed(store, "u_typed", MemoryKind.PREFERENCES)) == 12
    assert len(search_memory_typed(store, "u_typed", MemoryKind.EPISODES)) == 3
