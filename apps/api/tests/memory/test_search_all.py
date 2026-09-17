"""Instruction and preference reads return every stored row, however many pages it takes."""

from app.memory.store import (
    MemoryKind,
    get_instructions,
    get_store,
    search_memory,
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
    assert len(search_memory(store, "u_typed", MemoryKind.PREFERENCES)) == 12
    assert len(search_memory(store, "u_typed", MemoryKind.EPISODES)) == 3


def test_query_read_terminates_when_rows_have_no_embedding():
    """InMemoryStore ignores ``offset`` for unembedded rows; a queried read must still end."""
    store = get_store("sqlite:///:memory:")
    for i in range(120):
        store.put(("users", "u_noembed", "prefs"), f"k{i:03d}", {"note": f"n {i}"})
    for i in range(12):
        store.put(("users", "u_noembed", "prefs"), f"t{i:03d}", {"text": f"likes {i}"})

    result = search_preferences(store, "u_noembed", query="likes")

    texts = [row["text"] for row in result]
    assert len(texts) == len(set(texts))
    assert len(texts) <= 10


def test_unqueried_read_stops_when_a_store_ignores_offset():
    """A store that repeats the same full page forever yields each row once, then stops."""
    from types import SimpleNamespace

    from app.memory.store import _PAGE_SIZE, _read_all

    page = [
        SimpleNamespace(key=f"k{i}", value={"text": str(i)}) for i in range(_PAGE_SIZE)
    ]
    calls = []

    class RepeatingStore:
        def search(self, namespace, **kwargs):
            calls.append(kwargs["offset"])
            return list(page)

    items = _read_all(RepeatingStore(), ("users", "u", "prefs"))

    assert [item.key for item in items] == [item.key for item in page]
    assert calls == [0, _PAGE_SIZE]
