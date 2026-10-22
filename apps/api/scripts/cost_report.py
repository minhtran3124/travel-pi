#!/usr/bin/env python3
"""Report LLM cost coverage per month, flagging unpriced runs.

Groups ``agent_runs`` by calendar month into priced cost, the count and tokens
of NULL-cost (unpriced) runs with their models, and unpriced background tokens,
so an operator can reconcile against the provider invoice.

Run as a module from ``apps/api/``::

    python -m scripts.cost_report --since 30d
    python -m scripts.cost_report --since 24h

Exit codes: 0 ran; 2 usage error; 3 no runs in the window.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.pricing import is_priced, normalize_model
from app.db.engine import get_session_factory
from app.repositories.agent_run import AgentRunRepository


def _parse_since(value: str) -> timedelta:
    """Parse an ``Nd`` / ``Nh`` window into a ``timedelta``."""
    value = value.strip().lower()
    unit = value[-1:]
    if unit not in ("d", "h") or not value[:-1].isdigit():
        raise ValueError(f"Invalid --since {value!r}; use e.g. '30d' or '24h'.")
    n = int(value[:-1])
    return timedelta(days=n) if unit == "d" else timedelta(hours=n)


def build_report(rows) -> dict:
    """Group per-run cost rows by month (``created_at[:7]``); pure over *rows*."""
    agg: dict[str, dict] = defaultdict(
        lambda: {
            "runs": 0,
            "priced_cost_usd": 0.0,
            "unpriced_runs": 0,
            "unpriced_tokens": 0,
            "unpriced_models": set(),
            "background_tokens": 0,
        }
    )
    for r in rows:
        m = agg[r.created_at[:7]]
        m["runs"] += 1
        m["background_tokens"] += r.background_tokens or 0
        tokens = (r.input_tokens or 0) + (r.output_tokens or 0)
        if r.cost_usd is None and tokens:
            # A NULL-cost run with no tokens made no LLM call; it is not unpriced.
            m["unpriced_runs"] += 1
            m["unpriced_tokens"] += tokens
            for name in r.by_model or {}:
                if not is_priced(name):
                    m["unpriced_models"].add(normalize_model(name))
        elif r.cost_usd is not None:
            m["priced_cost_usd"] += r.cost_usd

    months = []
    for month in sorted(agg):
        m = agg[month]
        months.append(
            {
                "month": month,
                "runs": m["runs"],
                "priced_cost_usd": m["priced_cost_usd"],
                "unpriced_runs": m["unpriced_runs"],
                "unpriced_tokens": m["unpriced_tokens"],
                "unpriced_models": sorted(m["unpriced_models"]),
                "background_tokens": m["background_tokens"],
            }
        )
    return {"months": months}


def _print_table(
    report: dict,
    since: datetime,
) -> None:
    """Print the per-month coverage table plus the reconciliation footer; the month the window starts inside is marked ``*`` (partial)."""
    partial = since.strftime("%Y-%m")
    header = (
        f"{'month':<8} {'runs':>6} {'priced_usd':>12} {'unpriced':>9} "
        f"{'unpr_tokens':>12} {'bg_tokens':>10}  unpriced_models"
    )
    print(header)
    print("-" * len(header))
    for m in report["months"]:
        models = ", ".join(m["unpriced_models"]) or "-"
        print(
            f"{m['month'] + ('*' if m['month'] == partial else ''):<8} {m['runs']:>6} {m['priced_cost_usd']:>12.4f} "
            f"{m['unpriced_runs']:>9} {m['unpriced_tokens']:>12} "
            f"{m['background_tokens']:>10}  {models}"
        )
    print("-" * len(header))
    print(
        "Reconcile: compare each month's priced_usd with the provider invoice "
        "for the same month; unpriced runs and background_tokens are not costed."
    )
    if any(m["month"] == partial for m in report["months"]):
        print(
            f"* partial month: the window starts at {since.isoformat(timespec='minutes')}."
        )


def main(argv: list[str] | None = None) -> int:
    """Build and print the report; return the process exit code."""
    parser = argparse.ArgumentParser(description="Report LLM cost coverage per month.")
    parser.add_argument(
        "--since", default="30d", help="Window back from now (Nd / Nh, default 30d)."
    )
    args = parser.parse_args(argv)

    try:
        since = datetime.now(timezone.utc) - _parse_since(args.since)
    except (ValueError, OverflowError) as exc:
        # Surface a clean argparse usage error (exit 2), not a raw traceback.
        parser.error(f"Invalid --since {args.since!r}: {exc}")
    factory = get_session_factory(get_settings().database_url)
    rows = AgentRunRepository(factory).cost_rows_since(since)

    report = build_report(rows)
    if not report["months"]:
        print(f"no agent runs matched --since {args.since!r}; nothing to report.")
        return 3

    _print_table(report, since)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
