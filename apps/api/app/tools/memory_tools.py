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
from pydantic import Field

from app.memory.store import search_episodes, search_preferences, upsert_preference
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call


class SaveUserPreferenceArgs(AppBaseModel):
    key: str = Field(..., description="Preference key/name to store under.")
    text: str = Field(..., description="Free-text preference value.")


class GetUserPreferencesArgs(AppBaseModel):
    query: str | None = Field(None, description="Optional free-text filter.")


class RecallPastTripsArgs(AppBaseModel):
    query: str = Field(..., description="Free-text query to filter past trip episodes.")


@tool(args_schema=SaveUserPreferenceArgs)
def save_user_preference(
    key: str,
    text: str,
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Remember a traveller preference for future trips (e.g. diet, airline, pace).

    :param key: Preference key/name to store under.
    :param text: Free-text preference value.
    :param user_id: The traveller's id, injected from graph state (not model-supplied).
    :param store: The cross-session memory store, injected by LangGraph (not
        model-supplied).
    :return: Confirmation message.
    """
    log_tool_call(
        "save_user_preference", {"key": key, "text": text, "user_id": user_id}
    )
    upsert_preference(store, user_id, key, {"text": text})
    return f"Saved preference '{key}'."


@tool(args_schema=GetUserPreferencesArgs)
def get_user_preferences(
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
    query: str | None = None,
) -> list:
    """Recall the traveller's saved preferences (optionally filtered by a query).

    :param user_id: The traveller's id, injected from graph state (not model-supplied).
    :param store: The cross-session memory store, injected by LangGraph (not
        model-supplied).
    :param query: Optional free-text filter.
    :return: Matching saved preferences.
    """
    log_tool_call("get_user_preferences", {"user_id": user_id, "query": query})
    return search_preferences(store, user_id, query=query)


MEMORY_TOOLS = [save_user_preference, get_user_preferences]


@tool(args_schema=RecallPastTripsArgs)
def recall_past_trips(
    query: str,
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
) -> list:
    """Recall this traveller's past trip outcomes to personalise the plan (e.g.
    pace, area, airline/hotel preferences they liked before).

    :param query: Free-text query to filter past trip episodes.
    :param user_id: The traveller's id, injected from graph state (not model-supplied).
    :param store: The cross-session memory store, injected by LangGraph (not
        model-supplied).
    :return: Matching past-trip episodes.
    """
    log_tool_call("recall_past_trips", {"query": query, "user_id": user_id})
    return search_episodes(store, user_id, query=query)


# Episodic-recall tool, bound to the planner (gated by AgentContext.allow_episodic).
EPISODE_TOOLS = [recall_past_trips]
