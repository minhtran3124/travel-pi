"""Multi-turn eval harness + dataset registration (MIN-65 D9, Task 1.1)."""

import json

import pytest
from app.agents.graph import build_graph
from app.agents.suggestions import suggestions_for_flow
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.memory.store import search_preferences
from eval.harness import run_case
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _fake_graph(target="concierge", answer="here you go", checkpointer=None, store=None):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=target)],
        responses=[answer],
    )
    fast = FakeLLM(responses=["OK"])
    return build_graph(
        llm=main,
        fast_llm=fast,
        checkpointer=checkpointer or MemorySaver(),
        store=store or InMemoryStore(),
    )


class _SpyGraph:
    """Wraps a compiled graph, recording every invoke()'s payload + config."""

    def __init__(self, graph):
        self.graph = graph
        self.calls: list[dict] = []

    def invoke(self, payload, config, **kwargs):
        self.calls.append({"payload": payload, "config": config})
        return self.graph.invoke(payload, config, **kwargs)


# --- backward compatibility -------------------------------------------------


def test_single_turn_input_shape_still_works_unchanged():
    graph = _fake_graph(target="concierge", answer="hello there")
    res = run_case(graph, {"input": "hi"}, 0)

    assert res.test_case.input == "hi"
    assert res.current_flow == "concierge"
    assert res.test_case.actual_output == "hello there"


# --- multi-turn: shared thread accumulates state ----------------------------


def test_turns_share_one_thread_id_and_checkpoint_accumulates():
    checkpointer = MemorySaver()
    graph = _fake_graph(target="concierge", answer="reply", checkpointer=checkpointer)
    spy = _SpyGraph(graph)

    case = {"turns": ["turn one", "turn two", "turn three"]}
    res = run_case(spy, case, 0)

    thread_ids = [c["config"]["configurable"]["thread_id"] for c in spy.calls]
    assert len(spy.calls) == 3
    assert len(set(thread_ids)) == 1  # (a) same thread_id across all turns

    # (a) the checkpointer accumulated all 3 human turns under that one thread
    state = graph.get_state({"configurable": {"thread_id": thread_ids[0]}})
    human_texts = [
        m.content for m in state.values["messages"] if isinstance(m, HumanMessage)
    ]
    assert human_texts == ["turn one", "turn two", "turn three"]

    # actual_output is the LAST turn's reply
    assert res.test_case.actual_output == "reply"
    assert res.test_case.input == "Turn 1: turn one\nTurn 2: turn two\nTurn 3: turn three"


# --- multi-turn: new_thread_at opens a new thread, same user_id ------------


def test_new_thread_at_switches_thread_but_keeps_user_id_and_shares_store():
    store = InMemoryStore()
    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="journal"),
            SupervisorIntent(target_agent="concierge"),
        ],
        responses=["Here are some restaurant options."],
    )
    fast = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "save_user_preference",
                        "args": {"key": "diet", "text": "vegetarian"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Saved, I'll remember you're vegetarian."),
            "OK",  # reflection verdict, turn 0 (journal)
            "OK",  # reflection verdict, turn 1 (concierge)
        ]
    )
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )
    spy = _SpyGraph(graph)

    case = {
        "turns": ["I'm vegetarian, please remember", "Suggest a restaurant for me"],
        "new_thread_at": 1,
    }
    res = run_case(spy, case, 7)

    thread_ids = [c["config"]["configurable"]["thread_id"] for c in spy.calls]
    user_ids = [c["payload"]["user_id"] for c in spy.calls]

    assert thread_ids[0] != thread_ids[1]  # (b) new thread opened at index 1
    assert user_ids[0] == user_ids[1]  # ...but the same user_id throughout
    assert res.current_flow == "concierge"
    assert res.test_case.actual_output == "Here are some restaurant options."

    # (b) the preference saved in thread A is visible under the shared user_id
    # after the thread break — this is what makes cross-session recall
    # possible: it lives in the STORE, not the per-thread checkpoint.
    prefs = search_preferences(store, user_ids[0])
    assert any(p["text"] == "vegetarian" for p in prefs)

    # (b) thread B's checkpoint has no memory of turn 0's message — proves the
    # new thread is a genuinely fresh conversation, not a rename of thread A.
    state_b = graph.get_state({"configurable": {"thread_id": thread_ids[1]}})
    human_texts_b = [
        m.content for m in state_b.values["messages"] if isinstance(m, HumanMessage)
    ]
    assert human_texts_b == ["Suggest a restaurant for me"]


# --- suggestions attached to the final state --------------------------------


def test_run_case_attaches_suggestions_for_final_flow():
    graph = _fake_graph(target="planner", answer="Here's your itinerary")
    res = run_case(graph, {"turns": ["Plan my trip", "Add another day"]}, 3)

    assert res.test_case.metadata == {"suggestions": suggestions_for_flow("planner")}
    assert res.test_case.metadata["suggestions"]  # planner has non-empty suggestions


def test_run_case_attaches_empty_suggestions_for_unknown_flow():
    graph = _fake_graph(target="concierge", answer="ok")
    # Force an unrecognized flow to prove [] is returned, not a KeyError.
    res = run_case(graph, {"input": "hi"}, 0)
    assert isinstance(res.test_case.metadata["suggestions"], list)


# --- loader: new-shape validation -------------------------------------------


def test_loader_accepts_turns_shape(tmp_path, monkeypatch):
    import eval.loader as loader

    ds = tmp_path / "m.json"
    ds.write_text(
        json.dumps([{"turns": ["a", "b"], "new_thread_at": 1}]), encoding="utf-8"
    )
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)

    cases = loader.load("m.json")
    assert cases[0]["turns"] == ["a", "b"]
    assert cases[0]["new_thread_at"] == 1


def test_loader_accepts_turns_without_new_thread_at(tmp_path, monkeypatch):
    import eval.loader as loader

    ds = tmp_path / "m.json"
    ds.write_text(json.dumps([{"turns": ["a", "b"]}]), encoding="utf-8")
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)

    cases = loader.load("m.json")
    assert cases[0]["turns"] == ["a", "b"]


def test_loader_rejects_empty_turns(tmp_path, monkeypatch):
    import eval.loader as loader

    ds = tmp_path / "m.json"
    ds.write_text(json.dumps([{"turns": []}]), encoding="utf-8")
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)

    with pytest.raises(ValueError):
        loader.load("m.json")


def test_loader_rejects_non_string_turn(tmp_path, monkeypatch):
    import eval.loader as loader

    ds = tmp_path / "m.json"
    ds.write_text(json.dumps([{"turns": ["a", 1]}]), encoding="utf-8")
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)

    with pytest.raises(ValueError):
        loader.load("m.json")


@pytest.mark.parametrize("new_thread_at", [0, -1, 2])
def test_loader_rejects_new_thread_at_out_of_range(tmp_path, monkeypatch, new_thread_at):
    import eval.loader as loader

    ds = tmp_path / "m.json"
    ds.write_text(
        json.dumps([{"turns": ["a", "b"], "new_thread_at": new_thread_at}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)

    with pytest.raises(ValueError):
        loader.load("m.json")


def test_loader_rejects_non_int_new_thread_at(tmp_path, monkeypatch):
    import eval.loader as loader

    ds = tmp_path / "m.json"
    ds.write_text(
        json.dumps([{"turns": ["a", "b"], "new_thread_at": "1"}]), encoding="utf-8"
    )
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)

    with pytest.raises(ValueError):
        loader.load("m.json")


# --- loader: memory.json / suggestions.json registered ----------------------


def test_load_all_registers_memory_and_suggestions_datasets():
    from eval.loader import load_all

    all_ds = load_all()
    assert "memory.json" in all_ds
    assert "suggestions.json" in all_ds
    assert len(all_ds["memory.json"]) >= 8
    assert len(all_ds["suggestions.json"]) >= 8

    turn_cases = [c for c in all_ds["memory.json"] if "turns" in c]
    cross_session = [c for c in turn_cases if c.get("new_thread_at") is not None]
    assert len(cross_session) >= 2
