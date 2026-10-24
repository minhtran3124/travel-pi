"""Long-term memory tools; ``store`` and ``user_id`` are LangGraph-injected and hidden from the model
schema, so the LLM can never address another traveller's memory."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState, InjectedStore
from langgraph.store.base import BaseStore
from pydantic import ConfigDict, Field

from app.memory.guard import PREFERENCE_KEYS, MemoryRejected
from app.memory.store import search_episodes, search_preferences, upsert_preference
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call

logger = logging.getLogger(__name__)

# Returned (not raised) when the memory backend fails, so the model can carry on without it.
_UNAVAILABLE = "Memory is temporarily unavailable; continue without recalled memories."

# Closed enum of the canonical preference keys. Defined as a module-level alias
# (evaluated eagerly, unlike the string annotations produced by
# ``from __future__ import annotations``) so pydantic can resolve the forward ref
# from module globals when it builds ``SaveUserPreferenceArgs``.
# ``Literal[<tuple>]`` expands the tuple to one literal per member, identical to
# ``Literal[*PREFERENCE_KEYS]`` but without the star-in-subscript syntax that
# ruff's Python 3.10 target rejects.
PreferenceKey = Literal[PREFERENCE_KEYS]

# Model-facing description for the constrained preference key — lists the closed
# allowlist so the LLM picks a canonical key instead of inventing one that the
# guard would reject after the call (specs/memory-poisoning-hardening §3.3).
_PREFERENCE_KEY_DESC = (
    "Preference key to store under. Must be one of the allowed keys: "
    + ", ".join(PREFERENCE_KEYS)
    + "."
)

# NOTE: these tools take ``user_id``/``store`` as LangGraph-injected args
# (InjectedState/InjectedStore). Each explicit ``args_schema`` DECLARES them:
# ToolNode derives injection targets from the schema, so an injected param left
# out of it is never injected ("missing required positional arguments"). Declared,
# they are still stripped from the model-facing ``tool_call_schema``.


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
    key: PreferenceKey = Field(..., description=_PREFERENCE_KEY_DESC)
    text: str = Field(..., description="Free-text preference value.")


class GetUserPreferencesArgs(_MemoryInjectedArgs):
    query: str | None = Field(None, description="Optional free-text filter.")


class RecallPastTripsArgs(_MemoryInjectedArgs):
    query: str = Field(..., description="Free-text query to filter past trip episodes.")


@tool(args_schema=SaveUserPreferenceArgs)
def save_user_preference(
    key: Annotated[PreferenceKey, Field(description=_PREFERENCE_KEY_DESC)],
    text: Annotated[str, Field(description="Free-text preference value.")],
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Remember a traveller preference for future trips (e.g. diet, airline, pace).

    :param key: Preference key to store under; must be one of the canonical
        allowlist keys (an unknown key fails schema validation before the call).
    :param text: Free-text preference value.
    :param user_id: The traveller's id, injected from graph state (not model-supplied).
    :param store: The cross-session memory store, injected by LangGraph (not
        model-supplied).
    :return: Confirmation message, or a rejection message if the content guard
        (blocklist / length) refuses the value.
    """
    log_tool_call(
        "save_user_preference", {"key": key, "text": text, "user_id": user_id}
    )
    try:
        upsert_preference(store, user_id, key, {"text": text})
    except MemoryRejected as exc:
        # Content rejection (blocklist / length) — surface a plain message rather
        # than a raw exception (specs/memory-poisoning-hardening §3.3).
        return f"Could not save preference '{key}': {exc.reason}."
    except Exception:  # noqa: BLE001 - a dead store/embedding backend must not abort the turn
        logger.warning("save_user_preference failed", exc_info=True)
        return f"Could not save preference '{key}': memory is temporarily unavailable."
    return f"Saved preference '{key}'."


@tool(args_schema=GetUserPreferencesArgs)
def get_user_preferences(
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
    query: Annotated[
        str | None, Field(description="Optional free-text filter.")
    ] = None,
) -> list | str:
    """Recall the traveller's saved preferences (optionally filtered by a query).

    :param user_id: The traveller's id, injected from graph state (not model-supplied).
    :param store: The cross-session memory store, injected by LangGraph (not
        model-supplied).
    :param query: Optional free-text filter.
    :return: Matching saved preferences.
    """
    log_tool_call("get_user_preferences", {"user_id": user_id, "query": query})
    # Unqueried: every preference. With a query: the store's top semantic matches.
    try:
        return search_preferences(store, user_id, query=query)
    except Exception:  # noqa: BLE001 - a dead store/embedding backend must not abort the turn
        logger.warning("get_user_preferences failed", exc_info=True)
        return _UNAVAILABLE


MEMORY_TOOLS = [save_user_preference, get_user_preferences]


@tool(args_schema=RecallPastTripsArgs)
def recall_past_trips(
    query: Annotated[
        str, Field(description="Free-text query to filter past trip episodes.")
    ],
    user_id: Annotated[str, InjectedState("user_id")],
    store: Annotated[BaseStore, InjectedStore],
) -> list | str:
    """Recall this traveller's past trip outcomes to personalise the plan (e.g.
    pace, area, airline/hotel preferences they liked before).

    :param query: Free-text query to filter past trip episodes.
    :param user_id: The traveller's id, injected from graph state (not model-supplied).
    :param store: The cross-session memory store, injected by LangGraph (not
        model-supplied).
    :return: Matching past-trip episodes.
    """
    log_tool_call("recall_past_trips", {"query": query, "user_id": user_id})
    # Read 6 and keep 3 after the guard drops poisoned/legacy episodes.
    try:
        return search_episodes(store, user_id, query=query, limit=6)[:3]
    except Exception:  # noqa: BLE001 - a dead store/embedding backend must not abort the turn
        logger.warning("recall_past_trips failed", exc_info=True)
        return _UNAVAILABLE


# Episodic-recall tool, bound to the planner (gated by AgentContext.allow_episodic).
EPISODE_TOOLS = [recall_past_trips]
