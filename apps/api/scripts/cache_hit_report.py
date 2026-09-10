#!/usr/bin/env python3
"""Report OpenAI prompt-cache hit rates per node and model (specs/prompt-caching-system-prefix).

Aggregates the ``llm`` steps in ``agent_run_steps`` into a per node-and-model
table of cache hit rates (``cached_tokens`` / ``input_tokens``) so the caching
work of specs/prompt-caching-system-prefix can be measured against a real
database. An optional ``--min-ratio`` gates CI-style: the process exits 1 when
the overall hit rate is below the threshold.

Run as a module from ``apps/api/`` so ``app`` is importable:

    python -m scripts.cache_hit_report --since 7d
    python -m scripts.cache_hit_report --since 24h --node supervisor
    python -m scripts.cache_hit_report --since 7d --min-ratio 0.5

The gate is on the *overall* ratio, never per node: nodes whose system prompts
are under OpenAI's 1,024-token caching floor (``reflection``, ``synthesize``,
``summarize``) legitimately report a 0% hit rate, so a per-node gate would fail
on cache behaviour that is working as designed.

Runs against ``settings.database_url`` (so respects DATABASE_URL / .env). No
database password is read or printed by this script.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.repositories.agent_run import AgentRunRepository


def _ratio(cached: int, input_: int) -> float:
    """Cache hit rate ``cached / input``; 0.0 when there is no input."""
    return cached / input_ if input_ else 0.0


def _parse_since(value: str) -> timedelta:
    """Parse an ``Nd`` / ``Nh`` window into a ``timedelta``."""
    value = value.strip().lower()
    unit = value[-1:]
    if unit not in ("d", "h") or not value[:-1].isdigit():
        raise ValueError(f"Invalid --since {value!r}; use e.g. '7d' or '24h'.")
    n = int(value[:-1])
    return timedelta(days=n) if unit == "d" else timedelta(hours=n)


def build_report(rows) -> dict:
    """Aggregate ``llm`` step rows into per node-and-model hit-rate dicts.

    Pure over *rows* (each needs ``node``, ``model``, ``input_tokens``,
    ``cached_tokens``) so it is testable without a database.

    :param rows: The ``AgentRunStep`` rows (or equivalents) to aggregate.
    :return: ``{"rows": [...], "overall": float}`` where each row dict carries
        ``node, model, calls, input, cached, misses, ratio`` and ``overall`` is
        total cached / total input across every row.
    """
    agg: dict[tuple[str | None, str | None], dict] = defaultdict(
        lambda: {"calls": 0, "input": 0, "cached": 0}
    )
    for r in rows:
        a = agg[(r.node, r.model)]
        a["calls"] += 1
        a["input"] += r.input_tokens or 0
        a["cached"] += r.cached_tokens or 0

    report_rows = []
    total_input = total_cached = 0
    for (node, model), a in agg.items():
        total_input += a["input"]
        total_cached += a["cached"]
        report_rows.append(
            {
                "node": node,
                "model": model,
                "calls": a["calls"],
                "input": a["input"],
                "cached": a["cached"],
                "misses": a["input"] - a["cached"],
                "ratio": _ratio(a["cached"], a["input"]),
            }
        )
    report_rows.sort(key=lambda r: (r["node"] or "", r["model"] or ""))
    return {"rows": report_rows, "overall": _ratio(total_cached, total_input)}


def _print_table(report: dict) -> None:
    """Print the report as a fixed-width table plus the overall ratio."""
    header = f"{'node':<20} {'model':<24} {'calls':>6} {'input':>10} {'cached':>10} {'misses':>10} {'hit%':>7}"
    print(header)
    print("-" * len(header))
    for r in report["rows"]:
        print(
            f"{(r['node'] or '-'):<20} {(r['model'] or '-'):<24} {r['calls']:>6} "
            f"{r['input']:>10} {r['cached']:>10} {r['misses']:>10} {r['ratio'] * 100:>6.1f}%"
        )
    print("-" * len(header))
    print(f"overall hit rate: {report['overall'] * 100:.1f}%")


def main(argv: list[str] | None = None) -> int:
    """Build and print the report; return the process exit code."""
    parser = argparse.ArgumentParser(
        description="Report prompt-cache hit rates per node and model."
    )
    parser.add_argument(
        "--since", default="7d", help="Window back from now (Nd / Nh, default 7d)."
    )
    parser.add_argument("--node", help="Only report this node.")
    parser.add_argument(
        "--min-ratio",
        type=float,
        help="Exit 1 when the overall hit rate is below this ratio (0-1).",
    )
    args = parser.parse_args(argv)

    since = datetime.now(timezone.utc) - _parse_since(args.since)
    factory = get_session_factory(get_settings().database_url)
    rows = AgentRunRepository(factory).llm_steps_since(since)
    if args.node:
        rows = [r for r in rows if r.node == args.node]

    report = build_report(rows)
    _print_table(report)

    if args.min_ratio is not None and report["overall"] < args.min_ratio:
        print(
            f"overall hit rate {report['overall'] * 100:.1f}% is below "
            f"--min-ratio {args.min_ratio * 100:.1f}%"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
