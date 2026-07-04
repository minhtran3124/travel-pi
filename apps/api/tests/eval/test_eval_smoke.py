"""Eval harness smoke test (specs/travel-agent Task 8.1).

Drives the eval runner with a FakeLLM / in-memory store so CI exercises the
pipeline (and the threshold gates) with no API key or network.
"""


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
