"""Ledger early exit — a sub-agent blocked on the traveller abandons the
remaining ``pending_flows`` instead of draining them (MIN-68 / #99).

Wave 1: pure-code unit tests for the ``awaiting_user`` flag.
Wave 2 appends graph-level FakeLLM tests driving the ``needs_clarification`` tool.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.nodes import dispatch_next, load_context_node

# ---------------------------------------------------------------------------
# dispatch_next: awaiting_user short-circuits the ledger
# ---------------------------------------------------------------------------


def test_dispatch_next_awaiting_user_abandons_queue():
    cmd = dispatch_next(
        {"awaiting_user": True, "pending_flows": ["concierge", "budget"]}
    )
    assert cmd.goto == "reflection"
    assert cmd.update == {"pending_flows": []}


def test_dispatch_next_awaiting_user_with_empty_queue_still_reflects():
    cmd = dispatch_next({"awaiting_user": True, "pending_flows": []})
    assert cmd.goto == "reflection"


def test_dispatch_next_without_flag_drains_normally():
    cmd = dispatch_next({"pending_flows": ["concierge", "budget"]})
    assert cmd.goto == "concierge"
    assert cmd.update["current_flow"] == "concierge"
    assert cmd.update["pending_flows"] == ["budget"]


# ---------------------------------------------------------------------------
# load_context: the flag is single-turn — reset at the start of every turn
# ---------------------------------------------------------------------------


def test_load_context_resets_awaiting_user():
    result = load_context_node(
        {"trip_id": None, "user_id": None}, SimpleNamespace(store=None)
    )
    assert result["awaiting_user"] is False
    assert result["plan_approved"] is False  # existing reset stays intact
