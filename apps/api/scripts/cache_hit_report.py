#!/usr/bin/env python3
"""Report OpenAI prompt-cache hit rates per node and model.

Aggregates the ``llm`` steps in ``agent_run_steps`` into a per node-and-model
hit-rate table; ``--min-ratio`` gates CI-style on the overall ratio.

Run as a module from ``apps/api/``::

    python -m scripts.cache_hit_report --since 7d
    python -m scripts.cache_hit_report --since 24h --node supervisor
    python -m scripts.cache_hit_report --since 7d --min-ratio 0.5

Exit codes: 0 ran (or at/above threshold); 1 below ``--min-ratio``; 2 usage
error; 3 nothing measured (fails closed under ``--min-ratio``). The gate is on
the overall ratio, never per node — nodes under OpenAI's 1,024-token caching
floor legitimately report 0%.
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

    Pure over *rows* so it is testable without a database.
    """
    agg: dict[tuple[str | None, str | None], dict] = defaultdict(
        lambda: {"calls": 0, "input": 0, "cached": 0, "miss_calls": 0}
    )
    for r in rows:
        a = agg[(r.node, r.model)]
        a["calls"] += 1
        a["input"] += r.input_tokens or 0
        a["cached"] += r.cached_tokens or 0
        if not (r.cached_tokens or 0):
            a["miss_calls"] += 1

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
                "uncached": a["input"] - a["cached"],
                "miss_calls": a["miss_calls"],
                "ratio": _ratio(a["cached"], a["input"]),
            }
        )
    report_rows.sort(key=lambda r: (r["node"] or "", r["model"] or ""))
    return {"rows": report_rows, "overall": _ratio(total_cached, total_input)}


def _print_table(report: dict) -> None:
    """Print the report as a fixed-width table plus the overall ratio."""
    header = (
        f"{'node':<20} {'model':<24} {'calls':>6} {'input':>10} "
        f"{'cached':>10} {'uncached':>10} {'miss':>6} {'hit%':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in report["rows"]:
        print(
            f"{(r['node'] or '-'):<20} {(r['model'] or '-'):<24} {r['calls']:>6} "
            f"{r['input']:>10} {r['cached']:>10} {r['uncached']:>10} "
            f"{r['miss_calls']:>6} {r['ratio'] * 100:>6.1f}%"
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
        help="Exit 1 when the overall hit rate is below this ratio (0-1); exit 3 when nothing was measured.",
    )
    args = parser.parse_args(argv)

    try:
        window = _parse_since(args.since)
    except ValueError as exc:
        # Surface a clean argparse usage error (exit 2), not a raw traceback.
        parser.error(str(exc))
    since = datetime.now(timezone.utc) - window
    factory = get_session_factory(get_settings().database_url)
    rows = AgentRunRepository(factory).llm_steps_since(since)
    if args.node:
        rows = [r for r in rows if r.node == args.node]

    report = build_report(rows)

    total_input = sum(r["input"] for r in report["rows"])
    if not report["rows"] or total_input == 0:
        node_desc = f" and --node {args.node!r}" if args.node else ""
        if not report["rows"]:
            print(
                f"no LLM steps matched --since {args.since!r}{node_desc}; "
                "nothing to measure."
            )
        else:
            # Steps matched but none carried input tokens, so a hit rate would
            # be the 0.0 no-input sentinel, not a measurement.
            calls = sum(r["calls"] for r in report["rows"])
            print(
                f"{calls} LLM step(s) matched --since {args.since!r}{node_desc} "
                "but none carried input tokens; nothing to measure."
            )
        # Fail closed when a gate was requested: "no data" must not read as a
        # passing measurement.
        return 3 if args.min_ratio is not None else 0

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
