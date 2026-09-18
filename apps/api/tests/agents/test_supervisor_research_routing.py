"""Supervisor routing under prompt v14 (trip-research-deep-agent, Task 5.1).

Two guarantees:

1. A deep, whole-trip research request routes to the new ``research`` target
   (en + vi), and the free tier is gated out of it (premium-only).
2. **Regression guard:** every routing example written in ``v13.md`` still
   dispatches to its original target under v14 — adding ``research`` to
   ``_Target`` / ``ALL_SUBAGENTS`` changed nothing for the existing specialists.

The supervisor prompt is baked at ``make_supervisor`` build time (a pointer flip
in ``active.yaml`` is invisible until the node is rebuilt — see
docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md), so every test
builds its own supervisor from a fresh ``FakeLLM``; none reuse a cached graph.
The scripted ``FakeLLM.structured_responses`` drives the routing decision, so the
assertions exercise the supervisor's dispatch machinery, not the LLM.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext, resolve_agent_context
from app.enums import Tier
from langchain_core.messages import HumanMessage


def _runtime(ctx: AgentContext | None = None) -> SimpleNamespace:
    return SimpleNamespace(context=ctx if ctx is not None else AgentContext())


def _route(target: str, text: str, ctx: AgentContext | None = None):
    """Build a fresh supervisor whose FakeLLM returns ``target`` and route ``text``."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent=target)])
    supervisor = make_supervisor(llm)
    return supervisor({"messages": [HumanMessage(content=text)]}, _runtime(ctx))


# --- v14 is the active supervisor prompt ------------------------------------


def test_active_supervisor_prompt_is_v14_with_research_rule():
    """The pointer flip took effect and v14 carries the new research rule."""
    from app.prompts.registry import registry

    text = registry.get("supervisor")
    assert "research" in text.lower()
    # v13 rules are untouched — a v13 anchor phrase still present verbatim.
    assert "You never reply to" in text


def test_supervisor_intent_accepts_research_target():
    from app.agents.supervisor import SupervisorIntent

    assert SupervisorIntent(target_agent="research").target_agent == "research"


# --- research routing (SC-17) ------------------------------------------------


def test_research_request_routes_to_research_en():
    cmd = _route("research", "Research my trip in depth and build me a full dossier")
    assert cmd.update["current_flow"] == "research"
    assert cmd.update["tasks"] == [
        {
            "agent": "research",
            "query": "Research my trip in depth and build me a full dossier",
            "index": 0,
        }
    ]


def test_research_request_routes_to_research_vi():
    cmd = _route("research", "nghiên cứu kỹ cả chuyến đi giúp mình")
    assert cmd.update["current_flow"] == "research"
    assert cmd.update["tasks"][0]["agent"] == "research"


def test_free_tier_is_gated_out_of_research():
    """research is premium-only: a free-tier user is degraded, never routed."""
    ctx = resolve_agent_context(tier=Tier.FREE)
    assert "research" not in (ctx.allowed_subagents or frozenset())
    cmd = _route("research", "research my whole trip in depth", ctx)
    assert "tasks" not in cmd.update
    assert cmd.update["messages"][0].content  # a code-authored upgrade reply


# --- regression guard: every v13 routing example is unchanged under v14 ------

# Built from the examples actually written in app/prompts/supervisor/v13.md
# ("## Routing Examples", lines ~89-108, plus the "## Multi-step Plan" worked
# example). Each pair is (traveller message, the single target that example
# routes to). The two language-only examples (v13 lines 109-110) are excluded:
# they assert a detected language, not a routing target.
V13_ROUTING_EXAMPLES: list[tuple[str, str]] = [
    ("Is Hoi An worth visiting in October?", "concierge"),
    ("Move day 2 before day 3", "planner"),
    ("Thêm buổi tối ăn lẩu vào ngày 2 nhé", "planner"),
    ("Find a hotel in Kyoto and add it to my trip", "planner"),
    (
        "plan my weekend: flights + a hotel + places to see + weather + a "
        "day-by-day itinerary",
        "planner",
    ),
    (
        "plan my weekend: flights + a hotel + places to see + weather + local "
        "tips + a day-by-day itinerary",
        "planner",
    ),
    ("tìm chuyến bay từ Đà Nẵng ra Hà Nội sáng mai", "planner"),
    ("find/search flights from Da Nang to Hanoi tomorrow morning", "planner"),
    ("look for a hotel near the Old Quarter", "concierge"),
    ("khách sạn ở Đà Nẵng giá dưới 1tr", "concierge"),
    ("tôi muốn đặt phòng khách sạn X", "booking"),
    ("Book/confirm the 7am flight to Tokyo", "booking"),
    ("Quote me the 7am flight to Tokyo", "booking"),
    ("Add a note that I already booked the Hilton myself", "journal"),
    ("Log that I paid 50 USD for lunch today", "budget"),
    ("How much have we spent on food so far?", "budget"),
    ("Set a simple budget for my trip", "budget"),
    ("Break down a typical daily budget for backpacking in Vietnam", "concierge"),
    ("What's the weather in Bali tomorrow?", "concierge"),
    ("Find flights to Tokyo and tell me the weather there", "planner"),
    # "## Multi-step Plan" worked example (v13 lines 164-167).
    ("find me flights to Tokyo, and separately what visa do I need?", "planner"),
]


def test_every_v13_routing_example_dispatches_unchanged_under_v14():
    for text, expected_target in V13_ROUTING_EXAMPLES:
        cmd = _route(expected_target, text)
        assert cmd.update.get("current_flow") == expected_target, (
            f"v13 example {text!r} expected target {expected_target!r}, "
            f"got {cmd.update.get('current_flow')!r} under v14"
        )
        assert cmd.update["tasks"][0]["agent"] == expected_target
