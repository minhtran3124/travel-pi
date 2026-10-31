#!/usr/bin/env python3
"""Report LLM cost per turn, per user per day and per capability.

Reads ``agent_runs`` (``cost_usd``, tokens, ``current_flow``) and prints the
average cost per turn, per-user-per-day spend, a per-capability split, a
projected monthly cost per active user, and a check of
``agent_free_daily_turn_limit`` against the cost per turn. Unpriced runs (NULL
cost with tokens) are excluded from the averages and counted. No LLM calls.

Run as a module from ``apps/api/``::

    python -m scripts.turn_cost_report --since 30d

Exit codes: 0 ran; 2 usage error; 3 no runs in the window.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.repositories.agent_run import AgentRunRepository

_DAYS_PER_MONTH = 30


def _parse_since(value: str) -> timedelta:
    """Parse an ``Nd`` / ``Nh`` window into a ``timedelta``."""
    value = value.strip().lower()
    unit = value[-1:]
    if unit not in ("d", "h") or not value[:-1].isdigit():
        raise ValueError(f"Invalid --since {value!r}; use e.g. '30d' or '24h'.")
    n = int(value[:-1])
    return timedelta(days=n) if unit == "d" else timedelta(hours=n)


def build_report(rows, free_daily_turn_limit: int = 0) -> dict:
    """Aggregate per-run rows into cost stats; pure over *rows*.

    A run is priced when ``cost_usd`` is set, unpriced when it is NULL but made
    LLM calls (tokens), and ignored when it has no tokens and no cost (no LLM call).
    """
    unpriced = 0
    priced_cost = 0.0
    priced_turns = 0
    user_day: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"turns": 0, "cost": 0.0}
    )
    flows: dict[str, dict] = defaultdict(lambda: {"turns": 0, "cost": 0.0})
    for r in rows:
        has_tokens = (r.input_tokens or 0) + (r.output_tokens or 0) > 0
        if r.cost_usd is None:
            if has_tokens:
                unpriced += 1
            continue
        if not has_tokens and not r.cost_usd:
            # Zero cost with no tokens made no LLM call; not a priced turn.
            continue
        priced_turns += 1
        priced_cost += r.cost_usd
        ud = user_day[(r.user_id, r.created_at[:10])]
        ud["turns"] += 1
        ud["cost"] += r.cost_usd
        f = flows[r.current_flow or "unknown"]
        f["turns"] += 1
        f["cost"] += r.cost_usd

    avg_turn = priced_cost / priced_turns if priced_turns else 0.0
    users = {u for u, _ in user_day}
    days = sorted({d for _, d in user_day})
    user_day_costs = [v["cost"] for v in user_day.values()]
    avg_user_day = sum(user_day_costs) / len(user_day_costs) if user_day_costs else 0.0
    # Monthly cost of one active user = avg spend on a day they were active,
    # times the active days per month (30 assumes daily use: an upper bound).
    projected_month = avg_user_day * _DAYS_PER_MONTH
    capabilities = [
        {
            "capability": name,
            "turns": v["turns"],
            "cost_usd": v["cost"],
            "avg_cost_per_turn": v["cost"] / v["turns"],
        }
        for name, v in sorted(flows.items(), key=lambda kv: -kv[1]["cost"])
    ]
    return {
        "priced_turns": priced_turns,
        "unpriced_turns": unpriced,
        "total_cost_usd": priced_cost,
        "avg_cost_per_turn": avg_turn,
        "active_users": len(users),
        "active_days": len(days),
        "avg_cost_per_user_day": avg_user_day,
        "max_cost_per_user_day": max(user_day_costs, default=0.0),
        "capabilities": capabilities,
        "projected_monthly_cost_per_user": projected_month,
        "free_tier": {
            "daily_turn_limit": free_daily_turn_limit,
            "max_cost_per_user_day_usd": avg_turn * free_daily_turn_limit,
            "max_cost_per_user_month_usd": avg_turn
            * free_daily_turn_limit
            * _DAYS_PER_MONTH,
        },
    }


def _print_report(report: dict, since: datetime) -> None:
    """Print the report as plain text."""
    print(f"window start: {since.isoformat(timespec='minutes')}")
    print(
        f"priced turns: {report['priced_turns']}  "
        f"unpriced turns (excluded): {report['unpriced_turns']}"
    )
    print(f"total cost:             ${report['total_cost_usd']:.4f}")
    print(f"avg cost per turn:      ${report['avg_cost_per_turn']:.4f}")
    print(
        f"active users: {report['active_users']}  "
        f"avg cost per user per day: ${report['avg_cost_per_user_day']:.4f}  "
        f"max: ${report['max_cost_per_user_day']:.4f}"
    )
    print(
        "projected cost per active user per month: "
        f"${report['projected_monthly_cost_per_user']:.4f} "
        f"(avg active-day spend x {_DAYS_PER_MONTH})"
    )
    print()
    header = f"{'capability':<16} {'turns':>6} {'cost_usd':>10} {'avg/turn':>10}"
    print(header)
    print("-" * len(header))
    for c in report["capabilities"]:
        print(
            f"{c['capability']:<16} {c['turns']:>6} {c['cost_usd']:>10.4f} "
            f"{c['avg_cost_per_turn']:>10.4f}"
        )
    ft = report["free_tier"]
    print()
    print(
        f"free tier: agent_free_daily_turn_limit={ft['daily_turn_limit']} turns/day "
        f"x ${report['avg_cost_per_turn']:.4f}/turn = "
        f"${ft['max_cost_per_user_day_usd']:.4f}/user/day "
        f"(${ft['max_cost_per_user_month_usd']:.2f}/user/month worst case)"
    )


def main(argv: list[str] | None = None) -> int:
    """Build and print the report; return the process exit code."""
    parser = argparse.ArgumentParser(
        description="Report LLM cost per turn, user-day and capability."
    )
    parser.add_argument(
        "--since", default="30d", help="Window back from now (Nd / Nh, default 30d)."
    )
    args = parser.parse_args(argv)

    try:
        since = datetime.now(timezone.utc) - _parse_since(args.since)
    except (ValueError, OverflowError) as exc:
        parser.error(f"Invalid --since {args.since!r}: {exc}")
    settings = get_settings()
    factory = get_session_factory(settings.database_url)
    rows = AgentRunRepository(factory).turn_cost_rows_since(since)
    if not rows:
        print(f"no agent runs matched --since {args.since!r}; nothing to report.")
        return 3

    report = build_report(rows, settings.agent_free_daily_turn_limit)
    _print_report(report, since)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
