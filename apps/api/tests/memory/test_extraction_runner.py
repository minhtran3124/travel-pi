"""Unit tests for the framework-agnostic memory extraction runner."""

import json

from app.clients.llm import FakeLLM
from app.memory.extraction_runner import run_memory_extraction
from app.memory.store import get_instructions, search_episodes, search_preferences
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

MESSAGES = [
    HumanMessage(content="I love window seats and I'm vegetarian."),
    AIMessage(content="Noted — window seat, vegetarian meals."),
]

EXTRACTOR_JSON = json.dumps(
    {
        "preferences": [{"key": "seat", "text": "prefers window seats"}],
        "instructions": [{"key": "format", "text": "vegetarian meals only"}],
        "episodes": [
            {
                "key": "trip-1",
                "text": "booked a vegetarian-friendly trip",
                "city": "Hanoi",
            }
        ],
    }
)

EMPTY_JSON = json.dumps({"preferences": [], "instructions": [], "episodes": []})


class _RaisingLLM:
    """Minimal stub whose ``invoke`` raises — not a real BaseChatModel."""

    def invoke(self, messages):
        raise RuntimeError("boom")


def test_happy_path_writes_preference_instruction_episode():
    store = InMemoryStore()
    llm = FakeLLM(responses=[EXTRACTOR_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id="trip-1",
        plan_approved=False,
        allow_memory_write=True,
        store=store,
        llm=llm,
    )

    prefs = search_preferences(store, "u1")
    instrs = get_instructions(store, "u1")
    episodes = search_episodes(store, "u1")

    assert len(prefs) == 1
    assert prefs[0]["text"] == "prefers window seats"
    assert len(instrs) == 1
    assert instrs[0]["text"] == "vegetarian meals only"
    assert len(episodes) == 1
    assert episodes[0]["text"] == "booked a vegetarian-friendly trip"
    assert episodes[0]["city"] == "Hanoi"
    assert episodes[0]["trip_id"] == "trip-1"
    assert episodes[0]["outcome"] == "proposed"


def test_plan_approved_forces_episode_outcome_approved():
    store = InMemoryStore()
    llm = FakeLLM(responses=[EXTRACTOR_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id="trip-1",
        plan_approved=True,
        allow_memory_write=True,
        store=store,
        llm=llm,
    )

    episodes = search_episodes(store, "u1")
    assert len(episodes) == 1
    assert episodes[0]["outcome"] == "approved"


def test_allow_memory_write_false_writes_nothing():
    store = InMemoryStore()
    llm = FakeLLM(responses=[EXTRACTOR_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id="trip-1",
        plan_approved=False,
        allow_memory_write=False,
        store=store,
        llm=llm,
    )

    assert search_preferences(store, "u1") == []
    assert get_instructions(store, "u1") == []
    assert search_episodes(store, "u1") == []


def test_empty_extractor_json_writes_nothing():
    store = InMemoryStore()
    llm = FakeLLM(responses=[EMPTY_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id="trip-1",
        plan_approved=False,
        allow_memory_write=True,
        store=store,
        llm=llm,
    )

    assert search_preferences(store, "u1") == []
    assert get_instructions(store, "u1") == []
    assert search_episodes(store, "u1") == []


def test_raising_llm_is_swallowed_store_unchanged():
    store = InMemoryStore()
    llm = _RaisingLLM()

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id="trip-1",
        plan_approved=False,
        allow_memory_write=True,
        store=store,
        llm=llm,
    )

    assert search_preferences(store, "u1") == []
    assert get_instructions(store, "u1") == []
    assert search_episodes(store, "u1") == []


def test_no_user_id_or_store_writes_nothing():
    store = InMemoryStore()
    llm = FakeLLM(responses=[EXTRACTOR_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id=None,
        trip_id="trip-1",
        plan_approved=False,
        allow_memory_write=True,
        store=store,
        llm=llm,
    )
    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id="trip-1",
        plan_approved=False,
        allow_memory_write=True,
        store=None,
        llm=llm,
    )

    assert search_preferences(store, "u1") == []
