"""Long-term memory tools; ``store`` and ``user_id`` are LangGraph-injected and hidden from the model
schema, so the LLM can never address another traveller's memory."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState, InjectedStore
from langgraph.store.base import BaseStore
from pydantic import ConfigDict, Field

from app.memory.store import search_episodes, search_preferences, upsert_preference
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call

# Each args_schema must DECLARE the injected user_id/store: ToolNode derives injection targets from
# the schema, so omitting one breaks injection. They stay stripped from the model-facing schema.


class _MemoryInjectedArgs(AppBaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # BaseStore

    user_id: Annotated[str, InjectedState("user_id")] = Field(
        ...,
        description="The traveller's id. Injected from graph state — never "
        "supplied by the model.",
    )
    store: Annotated[BaseStore, InjectedStore] = Field(
        ..., description="The cross-session memory store. Injected by LangGraph."
    )


class SaveUserPreferenceArgs(_MemoryInjectedArgs):
    key: str = Field(..., description="Preference key/name to store under.")
    text: str = Field(..., description="Free-text preference value.")


class GetUserPreferencesArgs(_MemoryInjectedArgs):
    query: str | None = Field(None, description="Optional free-text filter.")


class RecallPastTripsArgs(_MemoryInjectedArgs):
    query: str = Field(..., description="Free-text query to filter past trip episodes.")


@tool(args_schema=SaveUserPreferenceArgs)
def save_user_preference(
    key: Annotated[str, Field(description="Preference key/name to store under.")],
    text: Annotated[str, Field(description="Free-text preference value.")],
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
    query: Annotated[
        str | None, Field(description="Optional free-text filter.")
    ] = None,
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
    query: Annotated[
        str, Field(description="Free-text query to filter past trip episodes.")
    ],
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
