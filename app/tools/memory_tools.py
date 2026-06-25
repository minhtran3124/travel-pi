"""Long-term memory tools (specs/travel-agent Task 3.4).

The journal sub-agent uses these to remember traveller preferences across
sessions. The store is injected by LangGraph at runtime via ``InjectedStore`` —
it is hidden from the model's tool schema, so the LLM only supplies the semantic
arguments. Backed by the cross-session ``app.memory.store`` helpers.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

from app.memory.store import search_preferences, upsert_preference


@tool
def save_user_preference(
    user_id: str,
    key: str,
    text: str,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Remember a traveller preference for future trips (e.g. diet, airline, pace)."""
    upsert_preference(store, user_id, key, {"text": text})
    return f"Saved preference '{key}' for user {user_id}."


@tool
def get_user_preferences(
    user_id: str,
    store: Annotated[BaseStore, InjectedStore],
    query: str | None = None,
) -> list:
    """Recall a traveller's saved preferences (optionally filtered by a query)."""
    return search_preferences(store, user_id, query=query)


MEMORY_TOOLS = [save_user_preference, get_user_preferences]
