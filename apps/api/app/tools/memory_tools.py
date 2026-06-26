"""Long-term memory tools (specs/travel-agent Task 3.4; agent-memory-semantic).

The journal sub-agent uses these to remember traveller preferences across sessions.
Both the ``store`` and the ``user_id`` are injected by LangGraph at runtime — the store
via ``InjectedStore`` and the user id via ``InjectedState`` (from the graph's
``TravelAgentState.user_id``). Both are hidden from the model's tool schema, so the LLM
only supplies the semantic arguments and can never address another traveller's memory
(REVIEW.md C3). Backed by the cross-session ``app.memory.store`` helpers.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState, InjectedStore
from langgraph.store.base import BaseStore

from app.memory.store import search_preferences, upsert_preference


@tool
def save_user_preference(
    key: str,
    text: str,
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Remember a traveller preference for future trips (e.g. diet, airline, pace)."""
    upsert_preference(store, user_id, key, {"text": text})
    return f"Saved preference '{key}'."


@tool
def get_user_preferences(
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
    query: str | None = None,
) -> list:
    """Recall the traveller's saved preferences (optionally filtered by a query)."""
    return search_preferences(store, user_id, query=query)


MEMORY_TOOLS = [save_user_preference, get_user_preferences]
