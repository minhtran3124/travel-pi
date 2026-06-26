"""Eval harness smoke test (specs/travel-agent Task 8.1).

Drives the eval runner with a FakeLLM / in-memory store so CI exercises the
pipeline (and the threshold gates) with no API key or network.
"""

from langchain_core.documents import Document


def test_routing_eval_pipeline_scores_and_gates():
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from eval.metrics import routing_accuracy
    from eval.run_eval import ROUTING_THRESHOLD, load_dataset, run_routing_eval

    dataset = load_dataset("routing.json")
    # Script the supervisor to return each expected agent in order -> 100%.
    fake = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent=item["expected"]) for item in dataset
        ]
    )
    results = run_routing_eval(fake, dataset)
    acc = routing_accuracy(results)
    assert acc == 1.0
    assert acc >= ROUTING_THRESHOLD


def test_routing_accuracy_detects_misroute():
    from eval.metrics import routing_accuracy

    results = [
        {"expected": "planner", "predicted": "planner"},
        {"expected": "budget", "predicted": "concierge"},
    ]
    assert routing_accuracy(results) == 0.5


def test_retrieval_eval_pipeline():
    from app.rag.embeddings import get_vector_store
    from eval.metrics import retrieval_hit_rate
    from eval.run_eval import RETRIEVAL_THRESHOLD, load_dataset, run_retrieval_eval

    store = get_vector_store(database_url="sqlite:///:memory:")
    store.add_documents(
        [
            Document(page_content="ramen shop in Shinjuku", metadata={"city": "Tokyo"}),
            Document(page_content="beach club", metadata={"city": "Da Nang"}),
        ]
    )
    dataset = load_dataset("rag.json")
    results = run_retrieval_eval(store, dataset)
    assert retrieval_hit_rate(results) >= RETRIEVAL_THRESHOLD
