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


def test_plan_eval_pipeline_scores_multi_intent():
    # P1: script the supervisor to emit each case's expected ordered plan and
    # confirm the run_plan_eval → plan_accuracy pipeline scores it 100% offline.
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from eval.metrics import plan_accuracy
    from eval.run_eval import PLAN_THRESHOLD, load_dataset, run_plan_eval

    dataset = load_dataset("multi_intent.json")
    fake = FakeLLM(
        structured_responses=[
            SupervisorIntent(
                target_agent=item["expected"],
                plan=item["expected_plan"] or None,
            )
            for item in dataset
        ]
    )
    results = run_plan_eval(fake, dataset)
    acc = plan_accuracy(results)
    assert acc == 1.0
    assert acc >= PLAN_THRESHOLD


def test_plan_accuracy_detects_wrong_order_and_target():
    from eval.metrics import plan_accuracy

    results = [
        # correct: target + ordered plan both match
        {
            "expected": "planner",
            "predicted": "planner",
            "expected_plan": ["concierge", "planner"],
            "predicted_plan": ["concierge", "planner"],
        },
        # wrong order of the plan → not correct
        {
            "expected": "planner",
            "predicted": "planner",
            "expected_plan": ["concierge", "planner"],
            "predicted_plan": ["planner", "concierge"],
        },
        # right plan but wrong target → not correct
        {
            "expected": "budget",
            "predicted": "concierge",
            "expected_plan": ["concierge"],
            "predicted_plan": ["concierge"],
        },
    ]
    assert plan_accuracy(results) == 1 / 3
